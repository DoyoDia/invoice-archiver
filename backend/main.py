from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

if __package__ is None or __package__ == "":
    # 允许通过 "python backend/main.py" 方式启动
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
) 
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from backend.app.auth import get_current_user, require_role
from backend.app.config import Settings, load_settings
from backend.app.db_session import DatabaseManager
from backend.app.dependencies import get_service, get_settings
from backend.app.models import User
from backend.app.schemas import (
    AnomalySchema,
    InvoiceDetailResponse,
    InvoiceEntity,
    InvoiceListItem,
    InvoiceListResponse,
    JobItem,
    JobQueryResponse,
    LineItemSchema,
    UploadResponse,
)
from backend.app.service_db import InvoiceServiceDB


def ensure_storage_dirs(root: Path) -> None:
    invoices_dir = root / "invoices"
    invoices_dir.mkdir(parents=True, exist_ok=True)
    (root / "tmp").mkdir(parents=True, exist_ok=True)


def decimal_to_str(value: Optional[Decimal], digits: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    if digits is not None:
        quant = Decimal("1").scaleb(-digits)
        return format(value.quantize(quant), f".{digits}f")
    return format(value.normalize(), "f")


def build_app() -> FastAPI:
    app = FastAPI(title="Invoice Archive API", version="1.0.0")

    settings = load_settings()
    base_dir = Path(__file__).resolve().parent
    storage_root = Path(settings.storage_root)
    if not storage_root.is_absolute():
        storage_root = (base_dir.parent / settings.storage_root).resolve()
    settings.storage_root = str(storage_root)
    ensure_storage_dirs(storage_root)

    db_manager = DatabaseManager(settings.database_url)
    
    async def get_session():
        async with db_manager.session() as session:
            yield session
    
    service = InvoiceServiceDB(settings, db_manager.session)

    app.state.settings = settings
    app.state.db_manager = db_manager
    app.state.service = service

    router = APIRouter(prefix="/api")

    @router.post(
        "/ingest/files",
        response_model=UploadResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def ingest_files(
        background_tasks: BackgroundTasks,
        current_user: User = Depends(require_role("uploader", "admin")),
        files: List[UploadFile] = File(..., alias="file"),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> UploadResponse:
        jobs = await service.ingest_files(files, current_user, background_tasks)
        return UploadResponse(
            jobs=[JobItem(job_id=job.job_id, file_id=job.file_id, status=job.status) for job in jobs]
        )

    @router.get("/jobs/{job_id}", response_model=JobQueryResponse)
    async def get_job(
        job_id: str,
        current_user: User = Depends(get_current_user),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> JobQueryResponse:
        job = await service.get_job(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        asset = await service.get_file_asset(job.file_id)
        if current_user.role != "admin" and asset and asset.uploader_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return JobQueryResponse(
            job_id=job.job_id,
            status=job.status,
            step=job.step,
            progress=job.progress,
            error=job.error,
            retry_count=job.retry_count,
            created_at=job.created_at,
            updated_at=job.updated_at,
            file_id=job.file_id,
        )

    @router.get("/invoices", response_model=InvoiceListResponse)
    async def list_invoices(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        invoice_no: Optional[str] = None,
        status_filter: Optional[str] = Query(None, alias="status"),
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        amount_min: Optional[str] = None,
        amount_max: Optional[str] = None,
        item_name: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> InvoiceListResponse:
        filters: Dict[str, Optional[str]] = {
            "invoice_no": invoice_no,
            "status": status_filter,
            "date_start": date_start,
            "date_end": date_end,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "item_name": item_name,
            "uploaded_by": (
                uploaded_by if current_user.role == "admin" else current_user.user_id if current_user.role == "uploader" else None
            ),
        }
        records, total = await service.list_invoices(page=page, page_size=page_size, filters=filters)
        items = [
            InvoiceListItem(
                invoice_id=record.id,
                invoice_no=record.invoice_no,
                invoice_date=record.invoice_date.isoformat() if record.invoice_date else None,
                buyer_name=record.buyer_name,
                seller_name=record.seller_name,
                total_amount=decimal_to_str(record.total_amount, 2),
                total_tax=decimal_to_str(record.total_tax, 2),
                grand_total=decimal_to_str(record.grand_total, 2),
                status=record.status.value,
                anomaly_codes=[an.code for an in record.anomalies],
                uploaded_at=record.created_at,
            )
            for record in records
        ]
        return InvoiceListResponse(items=items, page=page, page_size=page_size, total=total)

    @router.get("/invoices/{invoice_no}", response_model=InvoiceDetailResponse)
    async def get_invoice_detail(
        invoice_no: str,
        current_user: User = Depends(get_current_user),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> InvoiceDetailResponse:
        record = await service.get_invoice(invoice_no)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        if current_user.role == "uploader" and record.uploaded_by != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        invoice = InvoiceEntity(
            invoice_no=record.invoice_no,
            invoice_type=record.invoice_type,
            invoice_date=record.invoice_date.isoformat() if record.invoice_date else None,
            buyer=(
                {"name": record.buyer_name, "tax_id": record.buyer_tax_id}
                if record.buyer_name or record.buyer_tax_id
                else None
            ),
            seller=(
                {"name": record.seller_name, "tax_id": record.seller_tax_id}
                if record.seller_name or record.seller_tax_id
                else None
            ),
            totals={
                "amount": decimal_to_str(record.total_amount, 2),
                "tax": decimal_to_str(record.total_tax, 2),
                "grand": decimal_to_str(record.grand_total, 2),
            },
            status=record.status.value,
            source_file_id=record.source_file_id,
            created_at=record.created_at,
        )
        line_items = [
            LineItemSchema(
                item_name=item.item_name,
                spec_model=item.spec_model,
                quantity=decimal_to_str(item.quantity, 4),
                unit_price=decimal_to_str(item.unit_price, 6),
                amount=decimal_to_str(item.amount, 2),
                tax_rate=decimal_to_str(item.tax_rate, 2),
                tax_amount=decimal_to_str(item.tax_amount, 2),
            )
            for item in record.line_items
        ]
        anomalies = [
            AnomalySchema(
                severity=an.severity.value,
                code=an.code,
                message=an.message,
                field_path=an.field_path,
            )
            for an in record.anomalies
        ]
        return InvoiceDetailResponse(
            invoice=invoice,
            line_items=line_items,
            anomalies=anomalies,
            raw_ocr_json=record.raw_ocr_json,
        )

    @router.get("/export/invoices.csv")
    async def export_invoices_csv(
        invoice_no: Optional[str] = None,
        status_filter: Optional[str] = Query(None, alias="status"),
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        amount_min: Optional[str] = None,
        amount_max: Optional[str] = None,
        item_name: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> StreamingResponse:
        filters: Dict[str, Optional[str]] = {
            "invoice_no": invoice_no,
            "status": status_filter,
            "date_start": date_start,
            "date_end": date_end,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "item_name": item_name,
            "uploaded_by": (
                current_user.user_id if current_user.role == "uploader" else None
            ),
        }
        records, _ = await service.list_invoices(page=1, page_size=10000, filters=filters)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "invoice_id",
            "invoice_no",
            "invoice_date",
            "buyer_name",
            "seller_name",
            "total_amount",
            "total_tax",
            "grand_total",
            "status",
            "uploaded_at",
        ])
        for record in records:
            writer.writerow(
                [
                    record.id,
                    record.invoice_no,
                    record.invoice_date.isoformat() if record.invoice_date else "",
                    record.buyer_name or "",
                    record.seller_name or "",
                    decimal_to_str(record.total_amount, 2) or "",
                    decimal_to_str(record.total_tax, 2) or "",
                    decimal_to_str(record.grand_total, 2) or "",
                    record.status.value,
                    record.created_at.astimezone(timezone.utc).isoformat(),
                ]
            )
        output.seek(0)
        data = "\ufeff" + output.read()
        headers = {"Content-Disposition": "attachment; filename=invoices.csv"}
        return StreamingResponse(io.BytesIO(data.encode("utf-8")), media_type="text/csv; charset=utf-8", headers=headers)

    @router.get("/export/line_items.csv")
    async def export_line_items_csv(
        invoice_no: Optional[str] = None,
        status_filter: Optional[str] = Query(None, alias="status"),
        current_user: User = Depends(get_current_user),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> StreamingResponse:
        filters: Dict[str, Optional[str]] = {
            "invoice_no": invoice_no,
            "status": status_filter,
            "date_start": None,
            "date_end": None,
            "amount_min": None,
            "amount_max": None,
            "item_name": None,
            "uploaded_by": (
                current_user.user_id if current_user.role == "uploader" else None
            ),
        }
        records, _ = await service.list_invoices(page=1, page_size=10000, filters=filters)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "invoice_no",
            "invoice_date",
            "item_name",
            "spec_model",
            "quantity",
            "unit_price",
            "amount",
            "tax_rate",
            "tax_amount",
            "status",
        ])
        for record in records:
            for item in record.line_items:
                writer.writerow(
                    [
                        record.invoice_no,
                        record.invoice_date.isoformat() if record.invoice_date else "",
                        item.item_name or "",
                        item.spec_model or "",
                        decimal_to_str(item.quantity, 4) or "",
                        decimal_to_str(item.unit_price, 6) or "",
                        decimal_to_str(item.amount, 2) or "",
                        decimal_to_str(item.tax_rate, 2) or "",
                        decimal_to_str(item.tax_amount, 2) or "",
                        record.status.value,
                    ]
                )
        output.seek(0)
        data = "\ufeff" + output.read()
        headers = {"Content-Disposition": "attachment; filename=line_items.csv"}
        return StreamingResponse(io.BytesIO(data.encode("utf-8")), media_type="text/csv; charset=utf-8", headers=headers)

    @router.get("/files/{file_id}")
    async def download_file(
        file_id: int,
        current_user: User = Depends(get_current_user),
        service: InvoiceServiceDB = Depends(get_service),
    ) -> FileResponse:
        asset = await service.get_file_asset(file_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if current_user.role != "admin" and asset.uploader_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        if not asset.stored_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing")
        return FileResponse(
            asset.stored_path,
            media_type="application/pdf",
            filename=asset.filename,
        )

    @router.get("/health")
    async def health(settings: Settings = Depends(get_settings)) -> JSONResponse:
        now = datetime.now(timezone.utc)
        dependencies = {
            "database": "unknown",
            "redis": "unknown",
            "ocr": "ok" if settings.ocr_base_url else "unknown",
            "storage": "ok",
        }
        health_payload = {
            "status": "ok",
            "version": "1.0.0",
            "timestamp": now.isoformat(),
            "dependencies": dependencies,
        }
        return JSONResponse(content=health_payload)

    app.include_router(router)

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        await service.aclose()
        await db_manager.close()

    return app


app = build_app()