from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import AsyncContextManager, Callable, Dict, List, Optional, Tuple

from fastapi import BackgroundTasks, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import (
    AnomalySeverity,
    FileAsset,
    FileStatus,
    InvoiceAnomaly,
    InvoiceLineItem,
    InvoiceRecord,
    InvoiceStatus,
    JobRecord,
    User,
)
from .llm_service import LLMService
from .ocr import OCRClient
from .repository import InvoiceRepository
from ..md2json import parse_invoice_from_pdf_text, parse_invoice_from_ocr


class InvoiceServiceDB:
    def __init__(self, settings: Settings, session_factory: Callable[[], AsyncContextManager[AsyncSession]]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.ocr_client = OCRClient(settings)
        self._semaphore = asyncio.Semaphore(1)
        self.llm_service: Optional[LLMService] = None
        if self.settings.llm_enabled:
            try:
                self.llm_service = LLMService.from_settings(settings)
            except Exception:
                self.llm_service = None

    async def ingest_files(
        self,
        files: List[UploadFile],
        uploader: User,
        background_tasks: BackgroundTasks,
    ) -> List[JobRecord]:
        if not files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")

        jobs: List[JobRecord] = []
        for upload in files:
            job = await self._ingest_single_file(upload, uploader, background_tasks)
            jobs.append(job)
        return jobs

    async def _ingest_single_file(
        self,
        upload: UploadFile,
        uploader: User,
        background_tasks: BackgroundTasks,
    ) -> JobRecord:
        contents = await upload.read()
        if not contents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

        file_size = len(contents)
        max_bytes = self.settings.max_file_mb * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds max size")

        async with self.session_factory() as session:
            repo = InvoiceRepository(session)
            file_id = await repo.get_next_file_id()

            storage_root = Path(self.settings.storage_root)
            storage_root.mkdir(parents=True, exist_ok=True)
            invoices_dir = storage_root / "invoices"
            invoices_dir.mkdir(parents=True, exist_ok=True)

            filename = upload.filename or f"invoice_{file_id}.pdf"
            stored_path = invoices_dir / f"{file_id}_{filename}"
            stored_path.write_bytes(contents)

            sha256 = hashlib.sha256(contents).hexdigest()
            pages = self._count_pdf_pages(stored_path)
            if pages is not None and pages > self.settings.max_pages:
                stored_path.unlink(missing_ok=True)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Page limit exceeded")

            asset = FileAsset(
                id=file_id,
                filename=filename,
                content_hash=sha256,
                size=file_size,
                pages=pages,
                stored_path=stored_path,
                status=FileStatus.QUEUED,
                error=None,
                uploaded_at=datetime.now(timezone.utc),
                uploader_id=uploader.user_id,
            )
            await repo.create_file_asset(asset)

            job_id = uuid.uuid4().hex
            job = JobRecord(
                job_id=job_id,
                file_id=file_id,
                status="queued",
                step="waiting",
                progress=0.0,
                error=None,
                retry_count=0,
            )
            await repo.create_job(job)
            await session.commit()

        background_tasks.add_task(self._process_job, job_id)
        return job

    async def _process_job(self, job_id: str) -> None:
        async with self.session_factory() as session:
            repo = InvoiceRepository(session)
            job = await repo.get_job(job_id)
            if not job:
                return
            file_asset = await repo.get_file_asset(job.file_id)
            if not file_asset:
                return

            try:
                await self._update_job(repo, job, status="processing", step="extract_text", progress=0.1)
                await self._update_file(repo, file_asset, status=FileStatus.PROCESSING)
                await session.commit()

                parsed_json = None
                raw_text: Optional[str] = None

                # 优先尝试 LLM 解析（内置直接提取 + OCR 回退）
                if self.llm_service is not None:
                    await self._update_job(repo, job, step="llm_parse", progress=0.2)
                    await session.commit()
                    try:
                        llm_result = await self.llm_service.parse_invoice(file_asset.stored_path)
                        parsed_json = llm_result.data
                        raw_text = llm_result.source_markdown
                    except Exception as e:
                        # LLM 完全失败，记录错误（包含失败日志）
                        import json as json_lib
                        error_msg = str(e)
                        if "失败日志" in error_msg or "failure_logs" in error_msg:
                            # 错误信息已包含详细日志，直接记录
                            await self._update_job(repo, job, error=error_msg)
                        else:
                            await self._update_job(repo, job, error=f"LLM parse failed: {error_msg}")
                        parsed_json = None

                # 如果 LLM 未启用或失败，尝试传统方式
                if not parsed_json:
                    # 先尝试直接提取 PDF 文本
                    extracted_text = self._extract_pdf_text(file_asset.stored_path)

                    if extracted_text:
                        await self._update_job(repo, job, step="parse_extracted", progress=0.3)
                        await session.commit()

                        try:
                            candidate = parse_invoice_from_pdf_text(extracted_text)
                            if candidate.get("发票号码") or (candidate.get("项目") and len(candidate["项目"]) > 0):
                                parsed_json = candidate
                                raw_text = extracted_text
                        except Exception:
                            parsed_json = None

                # 如果仍未成功，使用 OCR
                if not parsed_json:
                    await self._update_job(repo, job, step="ocr", progress=0.4)
                    await session.commit()

                    async with self._semaphore:
                        ocr_result = await self.ocr_client.recognize_pdf(file_asset.stored_path)

                    await self._update_job(repo, job, step="parse", progress=0.6)
                    await session.commit()

                    parsed_json = parse_invoice_from_ocr(ocr_result.text)
                    raw_text = ocr_result.text
                
                # 确保 raw_text 不为 None
                if raw_text is None:
                    raise ValueError("Failed to extract text from PDF")

                await self._update_job(repo, job, step="validate", progress=0.7)
                await session.commit()

                invoice_record = await self._build_invoice_record(
                    repo=repo,
                    file_asset=file_asset,
                    parsed_json=parsed_json,
                    raw_text=raw_text,
                    uploader_id=file_asset.uploader_id,
                )

                await repo.create_invoice(invoice_record)
                await self._update_job(repo, job, status="finished", step="done", progress=1.0)
                await self._update_file(repo, file_asset, status=FileStatus.PROCESSED)
                await session.commit()
            except Exception as exc:
                await self._update_job(repo, job, status="failed", step="error", error=str(exc))
                await self._update_file(repo, file_asset, status=FileStatus.FAILED, error=str(exc))
                await session.commit()

    async def aclose(self) -> None:
        if self.llm_service is not None:
            try:
                await self.llm_service.aclose()
            except Exception:
                pass
        await self.ocr_client.aclose()

    async def _update_job(
        self,
        repo: InvoiceRepository,
        job: JobRecord,
        *,
        status: Optional[str] = None,
        step: Optional[str] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        if status is not None:
            job.status = status
        if step is not None:
            job.step = step
        if progress is not None:
            job.progress = progress
        if error is not None:
            job.error = error
        job.touch()
        await repo.update_job(job)

    async def _update_file(
        self,
        repo: InvoiceRepository,
        asset: FileAsset,
        *,
        status: Optional[FileStatus] = None,
        error: Optional[str] = None,
    ) -> None:
        if status is not None:
            asset.status = status
        if error is not None:
            asset.error = error
        await repo.update_file_asset(asset)

    async def _build_invoice_record(
        self,
        *,
        repo: InvoiceRepository,
        file_asset: FileAsset,
        parsed_json: Dict,
        raw_text: str,
        uploader_id: str,
    ) -> InvoiceRecord:
        invoice_id = await repo.get_next_invoice_id()
        invoice_no = (str(parsed_json.get("发票号码") or "").strip())
        invoice_type = (parsed_json.get("发票类型") or "").strip() or None
        invoice_date = self._parse_date(parsed_json.get("开票日期"))

        buyer_info = parsed_json.get("购买方信息", {}) or {}
        seller_info = parsed_json.get("销售方信息", {}) or {}
        totals = parsed_json.get("合计", {}) or {}
        grand_total_info = parsed_json.get("价税合计", {}) or {}

        line_items = self._parse_line_items(parsed_json.get("项目", []) or [])

        total_amount = self._parse_decimal(totals.get("金额"))
        total_tax = self._parse_decimal(totals.get("税额"))
        grand_total = self._parse_decimal(grand_total_info.get("小写"))

        anomalies: List[InvoiceAnomaly] = []
        status = InvoiceStatus.OK

        def flag(severity: AnomalySeverity, code: str, message: str, field: Optional[str] = None) -> None:
            nonlocal status
            anomalies.append(InvoiceAnomaly(severity=severity, code=code, message=message, field_path=field))
            if severity == AnomalySeverity.ERROR:
                status = InvoiceStatus.ERROR
            elif severity == AnomalySeverity.WARN and status == InvoiceStatus.OK:
                status = InvoiceStatus.WARN

        if not line_items:
            flag(AnomalySeverity.ERROR, "NULL_FIELD", "项目为空", "项目")

        allowed_rates = set(self.settings.allowed_tax_rates)
        for idx, item in enumerate(line_items, start=1):
            if not item.item_name:
                flag(AnomalySeverity.ERROR, "NULL_FIELD", "项目名称缺失", f"项目[{idx}].项目名称")
            if not item.spec_model:
                flag(AnomalySeverity.ERROR, "NULL_FIELD", "规格型号缺失", f"项目[{idx}].规格型号")
            if item.tax_rate is not None and allowed_rates and item.tax_rate not in allowed_rates:
                flag(AnomalySeverity.WARN, "TAX_RATE_ODD", "税率不在允许列表", f"项目[{idx}].税率")

        if grand_total is None:
            flag(AnomalySeverity.ERROR, "NULL_FIELD", "价税合计缺失", "价税合计.小写")
        elif total_amount is not None and total_tax is not None:
            difference = (total_amount + total_tax) - grand_total
            if abs(difference) > self.settings.amount_tolerance:
                flag(AnomalySeverity.ERROR, "SUM_MISMATCH", "金额不一致", "价税合计.小写")

        duplicates = await repo.find_invoices_by_no(invoice_no) if invoice_no else []
        final_status = status
        if invoice_no and duplicates:
            conflict = any(
                dup.grand_total != grand_total or dup.invoice_date != invoice_date for dup in duplicates
            )
            if conflict:
                final_status = InvoiceStatus.CONFLICT_DUPLICATE
                anomalies.append(
                    InvoiceAnomaly(
                        severity=AnomalySeverity.ERROR,
                        code="CONFLICTING_DUP",
                        message="同号发票金额或日期不一致",
                        field_path="发票号码",
                    )
                )
            else:
                if final_status in {InvoiceStatus.OK, InvoiceStatus.WARN}:
                    final_status = InvoiceStatus.DUPLICATE
                anomalies.append(
                    InvoiceAnomaly(
                        severity=AnomalySeverity.INFO,
                        code="DUPLICATE",
                        message="重复发票",
                        field_path="发票号码",
                    )
                )

        invoice_record = InvoiceRecord(
            id=invoice_id,
            invoice_no=invoice_no,
            invoice_type=invoice_type,
            invoice_date=invoice_date,
            buyer_name=(buyer_info.get("名称") or "").strip() or None,
            buyer_tax_id=(
                (buyer_info.get("纳税人识别号") or buyer_info.get("统一社会信用代码/纳税人识别号") or "").strip()
                or None
            ),
            seller_name=(seller_info.get("名称") or "").strip() or None,
            seller_tax_id=(
                (seller_info.get("纳税人识别号") or seller_info.get("统一社会信用代码/纳税人识别号") or "").strip()
                or None
            ),
            total_amount=total_amount,
            total_tax=total_tax,
            grand_total=grand_total,
            status=final_status,
            source_file_id=file_asset.id,
            raw_ocr_text=raw_text,
            raw_ocr_json=parsed_json,
            line_items=line_items,
            anomalies=anomalies,
            uploaded_by=uploader_id,
        )
        return invoice_record

    async def list_invoices(
        self,
        *,
        page: int,
        page_size: int,
        filters: Dict[str, Optional[str]],
    ) -> Tuple[List[InvoiceRecord], int]:
        async with self.session_factory() as session:
            repo = InvoiceRepository(session)
            return await repo.list_invoices(filters, page, page_size)

    async def get_invoice(self, invoice_no: str) -> Optional[InvoiceRecord]:
        async with self.session_factory() as session:
            repo = InvoiceRepository(session)
            return await repo.get_invoice_by_no(invoice_no)

    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        async with self.session_factory() as session:
            repo = InvoiceRepository(session)
            return await repo.get_job(job_id)

    async def get_file_asset(self, file_id: int) -> Optional[FileAsset]:
        async with self.session_factory() as session:
            repo = InvoiceRepository(session)
            return await repo.get_file_asset(file_id)

    def _parse_line_items(self, items: List[Dict]) -> List[InvoiceLineItem]:
        normalized: List[InvoiceLineItem] = []
        for entry in items:
            tax_rate = self._parse_decimal(entry.get("税率"))
            if tax_rate is None and isinstance(entry.get("税率"), str) and entry["税率"].endswith("%"):
                try:
                    tax_rate = Decimal(entry["税率"].rstrip("%"))
                except InvalidOperation:
                    tax_rate = None

            normalized.append(
                InvoiceLineItem(
                    item_name=(entry.get("项目名称") or "").strip() or None,
                    spec_model=(entry.get("规格型号") or "").strip() or None,
                    quantity=self._parse_decimal(entry.get("数量")),
                    unit_price=self._parse_decimal(entry.get("单价")),
                    amount=self._parse_decimal(entry.get("金额")),
                    tax_rate=tax_rate,
                    tax_amount=self._parse_decimal(entry.get("税额")),
                )
            )
        return normalized

    def _parse_decimal(self, value: Optional[str]) -> Optional[Decimal]:
        if value is None:
            return None
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        text = text.replace("¥", "")
        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    def _parse_date(self, value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        text = str(value).strip()
        for fmt in ("%Y年%m月%d日", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _count_pdf_pages(self, file_path: Path) -> Optional[int]:
        try:
            from pypdf import PdfReader

            with open(file_path, "rb") as fp:
                reader = PdfReader(fp)
                return len(reader.pages)
        except ImportError:
            return None
        except Exception:
            return None

    def _extract_pdf_text(self, file_path: Path) -> Optional[str]:
        """尝试从 PDF 提取文本，如果成功返回文本，失败返回 None"""
        try:
            from pypdf import PdfReader

            with open(file_path, "rb") as fp:
                reader = PdfReader(fp)
                text_parts = []
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                
                if text_parts:
                    full_text = "\n".join(text_parts)
                    # 简单检查是否包含发票相关关键字
                    if any(kw in full_text for kw in ["发票", "购买方", "销售方", "金额", "税额"]):
                        return full_text
                return None
        except Exception:
            return None
