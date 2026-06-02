from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, ContextManager, Dict, List, Optional, Tuple

import pymupdf
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .config import Settings
from .llm_service import LLMService
from .models import (
    FileAsset,
    FileStatus,
    InvoiceLineItem,
    InvoiceRecord,
    InvoiceStatus,
)
from .parser import parse_invoices
from .repository import InvoiceRepository


class InvoiceServiceDB:
    def __init__(self, settings: Settings, session_factory: Callable[[], ContextManager[Session]]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.llm: Optional[LLMService] = LLMService(settings) if settings.llm_enabled else None

    def ingest_files(self, files: List[UploadFile], tags: Optional[List[str]] = None) -> List[dict]:
        if not files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")
        tags = [t.strip() for t in (tags or []) if t.strip()]
        results: List[dict] = []
        for upload in files:
            results.extend(self._ingest_one(upload, tags))
        return results

    def _ingest_one(self, upload: UploadFile, tags: List[str]) -> List[dict]:
        contents = upload.file.read()
        if not contents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
        if len(contents) > self.settings.max_file_mb * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

        invoices_dir = Path(self.settings.storage_root) / "invoices"
        invoices_dir.mkdir(parents=True, exist_ok=True)
        filename = upload.filename or "invoice.pdf"

        with self.session_factory() as session:
            repo = InvoiceRepository(session)
            sha256 = hashlib.sha256(contents).hexdigest()
            pages = self._count_pages(contents)
            if pages is not None and pages > self.settings.max_pages:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page limit exceeded")

            asset = repo.create_file_asset(
                FileAsset(
                    id=None,
                    filename=filename,
                    content_hash=sha256,
                    size=len(contents),
                    pages=pages,
                    stored_path=Path("."),  # 占位，落盘后回填
                    status=FileStatus.PROCESSED,
                    error=None,
                )
            )
            stored_path = invoices_dir / f"{asset.id}_{filename}"
            stored_path.write_bytes(contents)
            repo.set_stored_path(asset.id, str(stored_path))

            try:
                parsed = self._parse(stored_path)
                if not parsed:
                    raise ValueError("未识别到发票")
                results: List[dict] = []
                for inv in parsed:
                    raw_text = inv.pop("_raw_text", "")
                    record = self._build_record(repo, asset.id, inv, raw_text, tags)
                    revived = repo.revive_if_deleted(record) if record.invoice_no else None
                    final = revived or repo.create_invoice(record)
                    results.append({
                        "file_id": asset.id,
                        "invoice_no": final.invoice_no,
                        "status": final.status.value,
                        "revived": revived is not None,
                    })
                return results
            except Exception as exc:
                repo.mark_failed(asset.id, str(exc))
                return [{"file_id": asset.id, "invoice_no": None, "status": "failed", "error": str(exc)}]

    def _parse(self, pdf_path: Path) -> List[dict]:
        """返回该 PDF 中的发票列表（合并发票拆分、多页合并）。"""
        parsed = parse_invoices(pdf_path)
        if any(self._is_valid(p) for p in parsed):
            return parsed
        # 正则未识别出有效发票时，尝试 LLM 兜底（仅按单张处理）
        if self.llm is not None:
            raw_text = self._extract_text(pdf_path)
            llm_parsed = self.llm.parse(raw_text)
            if llm_parsed and self._is_valid(llm_parsed):
                llm_parsed["_raw_text"] = raw_text
                return [llm_parsed]
        return parsed

    @staticmethod
    def _is_valid(data: dict) -> bool:
        if data.get("发票号码"):
            return True
        items = data.get("项目") or []
        return any(it.get("项目名称") for it in items)

    def _build_record(
        self, repo: InvoiceRepository, file_id: int, parsed: dict, raw_text: str, tags: List[str]
    ) -> InvoiceRecord:
        buyer = parsed.get("购买方信息") or {}
        seller = parsed.get("销售方信息") or {}
        totals = parsed.get("合计") or {}
        grand = parsed.get("价税合计") or {}

        invoice_no = str(parsed.get("发票号码") or "").strip()
        line_items = self._parse_line_items(parsed.get("项目") or [])
        total_amount = self._dec(totals.get("金额"))
        total_tax = self._dec(totals.get("税额"))
        grand_total = self._dec(grand.get("小写"))

        notes: List[str] = []
        record_status = InvoiceStatus.OK

        def warn(msg: str) -> None:
            nonlocal record_status
            notes.append(msg)
            if record_status == InvoiceStatus.OK:
                record_status = InvoiceStatus.WARN

        def error(msg: str) -> None:
            nonlocal record_status
            notes.append(msg)
            record_status = InvoiceStatus.ERROR

        if not invoice_no:
            error("发票号码缺失")
        if not line_items:
            error("项目为空")
        if grand_total is None:
            error("价税合计缺失")
        elif total_amount is not None and total_tax is not None:
            if abs((total_amount + total_tax) - grand_total) > self.settings.amount_tolerance:
                error("金额不一致：合计金额+税额 ≠ 价税合计")

        allowed = set(self.settings.allowed_tax_rates)
        for idx, item in enumerate(line_items, start=1):
            if item.tax_rate is not None and allowed and item.tax_rate not in allowed:
                warn(f"项目[{idx}]税率异常: {item.tax_rate}%")

        if invoice_no and repo.count_active_by_invoice_no(invoice_no) > 0:
            notes.append("重复发票号")
            if record_status in (InvoiceStatus.OK, InvoiceStatus.WARN):
                record_status = InvoiceStatus.DUPLICATE

        return InvoiceRecord(
            id=None,
            invoice_no=invoice_no,
            invoice_type=(parsed.get("发票类型") or "").strip() or None,
            invoice_date=self._date(parsed.get("开票日期")),
            buyer_name=(buyer.get("名称") or "").strip() or None,
            buyer_tax_id=(buyer.get("纳税人识别号") or "").strip() or None,
            seller_name=(seller.get("名称") or "").strip() or None,
            seller_tax_id=(seller.get("纳税人识别号") or "").strip() or None,
            total_amount=total_amount,
            total_tax=total_tax,
            grand_total=grand_total,
            status=record_status,
            notes="; ".join(notes) or None,
            source_file_id=file_id,
            raw_text=raw_text,
            raw_json=parsed,
            line_items=line_items,
            tags=list(tags),
            created_at=datetime.now(),  # 上传时间（本地时区，容器由 TZ 环境变量决定）
        )

    def list_invoices(
        self, *, page: int, page_size: int, filters: Dict[str, Optional[str]], include_deleted: bool = True
    ) -> Tuple[List[InvoiceRecord], int]:
        with self.session_factory() as session:
            return InvoiceRepository(session).list_invoices(filters, page, page_size, include_deleted)

    def get_invoice(self, invoice_no: str) -> Optional[InvoiceRecord]:
        with self.session_factory() as session:
            return InvoiceRepository(session).get_invoice_by_no(invoice_no)

    def get_file_asset(self, file_id: int) -> Optional[FileAsset]:
        with self.session_factory() as session:
            return InvoiceRepository(session).get_file_asset(file_id)

    def status_counts(self) -> Dict[str, int]:
        with self.session_factory() as session:
            return InvoiceRepository(session).status_counts()

    # --- 标签 / 软删除 ---

    def list_tags(self, q: Optional[str] = None) -> List[dict]:
        with self.session_factory() as session:
            return [{"id": i, "name": n} for i, n in InvoiceRepository(session).list_tags(q)]

    def create_tag(self, name: str) -> dict:
        with self.session_factory() as session:
            i, n = InvoiceRepository(session).create_tag(name)
            return {"id": i, "name": n}

    def delete_tag(self, tag_id: int) -> bool:
        with self.session_factory() as session:
            return InvoiceRepository(session).delete_tag(tag_id)

    def set_invoice_tags(self, invoice_no: str, names: List[str]) -> Optional[InvoiceRecord]:
        with self.session_factory() as session:
            return InvoiceRepository(session).set_invoice_tags(invoice_no, names)

    def set_deleted(self, invoice_no: str, deleted: bool) -> Optional[InvoiceRecord]:
        with self.session_factory() as session:
            return InvoiceRepository(session).set_deleted(invoice_no, deleted)

    def _parse_line_items(self, items: List[Dict]) -> List[InvoiceLineItem]:
        result: List[InvoiceLineItem] = []
        for entry in items:
            rate_raw = entry.get("税率")
            tax_rate = self._dec(str(rate_raw).rstrip("%")) if rate_raw else None
            result.append(
                InvoiceLineItem(
                    item_name=(entry.get("项目名称") or "").strip() or None,
                    spec_model=(entry.get("规格型号") or "").strip() or None if entry.get("规格型号") else None,
                    quantity=self._dec(entry.get("数量")),
                    unit_price=self._dec(entry.get("单价")),
                    amount=self._dec(entry.get("金额")),
                    tax_rate=tax_rate,
                    tax_amount=self._dec(entry.get("税额")),
                )
            )
        return result

    @staticmethod
    def _dec(value) -> Optional[Decimal]:
        if value is None:
            return None
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))
        text = str(value).strip().replace(",", "").replace("¥", "")
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    @staticmethod
    def _date(value) -> Optional[date]:
        if not value:
            return None
        for fmt in ("%Y年%m月%d日", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(str(value).strip(), fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _count_pages(contents: bytes) -> Optional[int]:
        try:
            with pymupdf.open(stream=contents, filetype="pdf") as doc:
                return doc.page_count
        except Exception:
            return None

    @staticmethod
    def _extract_text(pdf_path: Path) -> str:
        try:
            with pymupdf.open(str(pdf_path)) as doc:
                return "\n".join(page.get_text() for page in doc)
        except Exception:
            return ""
