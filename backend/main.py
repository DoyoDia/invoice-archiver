from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parent.parent))

import os

from fastapi import APIRouter, Body, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


class SPAStaticFiles(StaticFiles):
    """前端为单页应用：对路由型路径（无扩展名、非 /api）的 404 回退到 index.html，
    使刷新 /upload、/invoices/{no} 等子路由不再 404；静态资源与 API 的 404 照常。"""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            last = path.rsplit("/", 1)[-1]
            if exc.status_code == 404 and not path.startswith("api") and "." not in last:
                return await super().get_response("index.html", scope)
            raise

from backend.app.config import load_settings
from backend.app.db_session import DatabaseManager
from backend.app.dependencies import get_service, get_settings
from backend.app.schemas import (
    CreateTagRequest,
    IngestResultItem,
    InvoiceDetailResponse,
    InvoiceEntity,
    InvoiceListItem,
    InvoiceListResponse,
    LineItemSchema,
    SetDeletedRequest,
    SetTagsRequest,
    TagItem,
    UploadResponse,
)
from backend.app.service_db import InvoiceServiceDB


def decimal_to_str(value: Optional[Decimal], digits: int = 2) -> Optional[str]:
    if value is None:
        return None
    quant = Decimal("1").scaleb(-digits)
    return format(value.quantize(quant), f".{digits}f")


def _filters(invoice_no, status_filter, date_start, date_end, tag=None) -> Dict[str, Optional[str]]:
    return {
        "invoice_no": invoice_no,
        "status": status_filter,
        "date_start": date_start,
        "date_end": date_end,
        "tag": tag,
    }


def build_app() -> FastAPI:
    app = FastAPI(title="Invoice Archive API", version="2.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    settings = load_settings()
    base_dir = Path(__file__).resolve().parent
    storage_root = Path(settings.storage_root)
    if not storage_root.is_absolute():
        storage_root = (base_dir.parent / settings.storage_root).resolve()
    settings.storage_root = str(storage_root)
    (storage_root / "invoices").mkdir(parents=True, exist_ok=True)

    db_url = settings.database_url
    if db_url.startswith("sqlite:///./"):
        db_url = f"sqlite:///{storage_root / 'invoices.db'}"
    db_manager = DatabaseManager(db_url)
    service = InvoiceServiceDB(settings, db_manager.session)

    app.state.settings = settings
    app.state.db_manager = db_manager
    app.state.service = service

    router = APIRouter(prefix="/api")

    @router.post("/invoices", response_model=UploadResponse)
    def upload_invoices(
        files: List[UploadFile] = File(..., alias="file"),
        tags: List[str] = Form(default=[]),
        skip_dup: bool = Form(False),
        skip_dup_in_tag: bool = Form(False),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> UploadResponse:
        results = service.ingest_files(files, tags, skip_dup, skip_dup_in_tag)
        return UploadResponse(results=[IngestResultItem(**r) for r in results])

    @router.get("/invoices", response_model=InvoiceListResponse)
    def list_invoices(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        invoice_no: Optional[str] = None,
        status_filter: Optional[str] = Query(None, alias="status"),
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        tag: Optional[str] = None,
        service: InvoiceServiceDB = Depends(get_service),
    ) -> InvoiceListResponse:
        records, total = service.list_invoices(
            page=page,
            page_size=page_size,
            filters=_filters(invoice_no, status_filter, date_start, date_end, tag),
        )
        items = [
            InvoiceListItem(
                invoice_id=r.id,
                invoice_no=r.invoice_no,
                invoice_date=r.invoice_date.isoformat() if r.invoice_date else None,
                buyer_name=r.buyer_name,
                seller_name=r.seller_name,
                total_amount=decimal_to_str(r.total_amount),
                total_tax=decimal_to_str(r.total_tax),
                grand_total=decimal_to_str(r.grand_total),
                status=r.status.value,
                deleted=r.deleted,
                tags=r.tags,
                source_file_id=r.source_file_id,
                uploaded_at=r.created_at,
            )
            for r in records
        ]
        return InvoiceListResponse(items=items, page=page, page_size=page_size, total=total)

    @router.get("/invoices/summary")
    def invoices_summary(service: InvoiceServiceDB = Depends(get_service)) -> Dict[str, int]:
        return service.status_counts()

    @router.get("/tags", response_model=List[TagItem])
    def list_tags(q: Optional[str] = None, service: InvoiceServiceDB = Depends(get_service)) -> List[TagItem]:
        return [TagItem(**t) for t in service.list_tags(q)]

    @router.post("/tags", response_model=TagItem)
    def create_tag(body: CreateTagRequest, service: InvoiceServiceDB = Depends(get_service)) -> TagItem:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标签名不能为空")
        return TagItem(**service.create_tag(name))

    @router.delete("/tags/{tag_id}")
    def delete_tag(tag_id: int, service: InvoiceServiceDB = Depends(get_service)) -> Dict[str, bool]:
        if not service.delete_tag(tag_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return {"ok": True}

    @router.put("/tags/{tag_id}", response_model=TagItem)
    def rename_tag(
        tag_id: int, body: CreateTagRequest, service: InvoiceServiceDB = Depends(get_service)
    ) -> TagItem:
        try:
            result = service.rename_tag(tag_id, body.name)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return TagItem(**result)

    @router.put("/invoices/{invoice_no}/tags")
    def set_invoice_tags(
        invoice_no: str, body: SetTagsRequest, service: InvoiceServiceDB = Depends(get_service)
    ) -> Dict[str, object]:
        record = service.set_invoice_tags(invoice_no, body.tags)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        return {"ok": True, "tags": record.tags}

    @router.post("/invoices/{invoice_no}/deleted")
    def set_invoice_deleted(
        invoice_no: str, body: SetDeletedRequest, service: InvoiceServiceDB = Depends(get_service)
    ) -> Dict[str, object]:
        record = service.set_deleted(invoice_no, body.deleted)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        return {"ok": True, "deleted": record.deleted}

    @router.get("/invoices/{invoice_no}", response_model=InvoiceDetailResponse)
    def get_invoice_detail(
        invoice_no: str,
        service: InvoiceServiceDB = Depends(get_service),
    ) -> InvoiceDetailResponse:
        record = service.get_invoice(invoice_no)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        invoice = InvoiceEntity(
            invoice_no=record.invoice_no,
            invoice_type=record.invoice_type,
            invoice_date=record.invoice_date.isoformat() if record.invoice_date else None,
            buyer={"name": record.buyer_name, "tax_id": record.buyer_tax_id},
            seller={"name": record.seller_name, "tax_id": record.seller_tax_id},
            totals={
                "amount": decimal_to_str(record.total_amount),
                "tax": decimal_to_str(record.total_tax),
                "grand": decimal_to_str(record.grand_total),
            },
            status=record.status.value,
            notes=record.notes,
            deleted=record.deleted,
            tags=record.tags,
            source_file_id=record.source_file_id,
            created_at=record.created_at,
        )
        line_items = [
            LineItemSchema(
                item_name=i.item_name,
                spec_model=i.spec_model,
                quantity=decimal_to_str(i.quantity, 4),
                unit_price=decimal_to_str(i.unit_price, 6),
                amount=decimal_to_str(i.amount),
                tax_rate=decimal_to_str(i.tax_rate),
                tax_amount=decimal_to_str(i.tax_amount),
            )
            for i in record.line_items
        ]
        return InvoiceDetailResponse(invoice=invoice, line_items=line_items, raw_json=record.raw_json)

    @router.get("/export.csv")
    def export_csv(
        invoice_no: Optional[str] = None,
        status_filter: Optional[str] = Query(None, alias="status"),
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        tag: Optional[str] = None,
        quote_no: bool = Query(False),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> StreamingResponse:
        # 导出排除已标记删除的发票
        records, _ = service.list_invoices(
            page=1,
            page_size=100000,
            filters=_filters(invoice_no, status_filter, date_start, date_end, tag),
            include_deleted=False,
        )
        # 同号去重：records 已按上传时间倒序，保留每个发票号最新的一条
        # （重新导入修正过的版本胜出，避免旧异常/重复记录污染导出）
        seen: set = set()
        deduped = []
        for r in records:
            if r.invoice_no and r.invoice_no in seen:
                continue
            if r.invoice_no:
                seen.add(r.invoice_no)
            deduped.append(r)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "invoice_no", "invoice_date", "buyer_name", "seller_name",
            "total_amount", "total_tax", "grand_total", "status",
        ])
        for r in deduped:
            # quote_no=True 时在发票号前加单引号，避免老版本 Excel 转成科学计数法
            invoice_cell = f"'{r.invoice_no}" if quote_no else r.invoice_no
            writer.writerow([
                invoice_cell,
                r.invoice_date.isoformat() if r.invoice_date else "",
                r.buyer_name or "",
                r.seller_name or "",
                decimal_to_str(r.total_amount) or "",
                decimal_to_str(r.total_tax) or "",
                decimal_to_str(r.grand_total) or "",
                r.status.value,
            ])
        data = ("﻿" + output.getvalue()).encode("utf-8")
        filename = "invoices_quoted.csv" if quote_no else "invoices.csv"
        headers = {"Content-Disposition": f"attachment; filename={filename}"}
        return StreamingResponse(io.BytesIO(data), media_type="text/csv; charset=utf-8", headers=headers)

    @router.get("/files/{file_id}")
    def download_file(
        file_id: int,
        service: InvoiceServiceDB = Depends(get_service),
    ) -> FileResponse:
        asset = service.get_file_asset(file_id)
        if not asset or not asset.stored_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return FileResponse(asset.stored_path, media_type="application/pdf", filename=asset.filename)

    @router.get("/health")
    def health(settings=Depends(get_settings)) -> Dict[str, object]:
        return {
            "status": "ok",
            "version": "2.0.0",
            "llm_fallback": settings.llm_enabled,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    app.include_router(router)

    frontend_dist = os.getenv("FRONTEND_DIST", str(base_dir.parent / "frontend" / "dist"))
    if Path(frontend_dist).is_dir():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    @app.on_event("shutdown")
    def shutdown_event() -> None:
        db_manager.close()

    return app


app = build_app()
