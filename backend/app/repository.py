from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .database import FileAssetDB, InvoiceAnomalyDB, InvoiceDB, JobRecordDB, LineItemDB
from .models import (
    AnomalySeverity,
    FileAsset,
    FileStatus,
    InvoiceAnomaly,
    InvoiceLineItem,
    InvoiceRecord,
    InvoiceStatus,
    JobRecord,
)


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_file_asset(self, asset: FileAsset) -> FileAsset:
        db_asset = FileAssetDB(
            id=asset.id,
            filename=asset.filename,
            content_hash=asset.content_hash,
            size=asset.size,
            pages=asset.pages,
            stored_path=str(asset.stored_path),
            status=asset.status,
            error=asset.error,
            uploaded_at=asset.uploaded_at,
            uploader_id=asset.uploader_id,
        )
        self.session.add(db_asset)
        await self.session.flush()
        return asset

    async def update_file_asset(self, asset: FileAsset) -> None:
        stmt = select(FileAssetDB).where(FileAssetDB.id == asset.id)
        result = await self.session.execute(stmt)
        db_asset = result.scalar_one_or_none()
        if db_asset:
            db_asset.status = asset.status
            db_asset.error = asset.error
            await self.session.flush()

    async def get_file_asset(self, file_id: int) -> Optional[FileAsset]:
        stmt = select(FileAssetDB).where(FileAssetDB.id == file_id)
        result = await self.session.execute(stmt)
        db_asset = result.scalar_one_or_none()
        if not db_asset:
            return None
        return FileAsset(
            id=db_asset.id,
            filename=db_asset.filename,
            content_hash=db_asset.content_hash,
            size=db_asset.size,
            pages=db_asset.pages,
            stored_path=Path(db_asset.stored_path),
            status=FileStatus(db_asset.status),
            error=db_asset.error,
            uploaded_at=db_asset.uploaded_at,
            uploader_id=db_asset.uploader_id,
        )

    async def create_job(self, job: JobRecord) -> JobRecord:
        db_job = JobRecordDB(
            job_id=job.job_id,
            file_id=job.file_id,
            status=job.status,
            step=job.step,
            progress=float(job.progress),
            error=job.error,
            retry_count=job.retry_count,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        self.session.add(db_job)
        await self.session.flush()
        return job

    async def update_job(self, job: JobRecord) -> None:
        stmt = select(JobRecordDB).where(JobRecordDB.job_id == job.job_id)
        result = await self.session.execute(stmt)
        db_job = result.scalar_one_or_none()
        if db_job:
            db_job.status = job.status
            db_job.step = job.step
            db_job.progress = float(job.progress)
            db_job.error = job.error
            db_job.retry_count = job.retry_count
            db_job.updated_at = job.updated_at
            await self.session.flush()

    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        stmt = select(JobRecordDB).where(JobRecordDB.job_id == job_id)
        result = await self.session.execute(stmt)
        db_job = result.scalar_one_or_none()
        if not db_job:
            return None
        return JobRecord(
            job_id=db_job.job_id,
            file_id=db_job.file_id,
            status=db_job.status,
            step=db_job.step,
            progress=float(db_job.progress),
            error=db_job.error,
            retry_count=db_job.retry_count,
            created_at=db_job.created_at,
            updated_at=db_job.updated_at,
        )

    async def create_invoice(self, invoice: InvoiceRecord) -> InvoiceRecord:
        db_invoice = InvoiceDB(
            id=invoice.id,
            invoice_no=invoice.invoice_no,
            invoice_type=invoice.invoice_type,
            invoice_date=invoice.invoice_date,
            buyer_name=invoice.buyer_name,
            buyer_tax_id=invoice.buyer_tax_id,
            seller_name=invoice.seller_name,
            seller_tax_id=invoice.seller_tax_id,
            total_amount=invoice.total_amount,
            total_tax=invoice.total_tax,
            grand_total=invoice.grand_total,
            status=invoice.status,
            source_file_id=invoice.source_file_id,
            raw_ocr_text=invoice.raw_ocr_text,
            raw_ocr_json=invoice.raw_ocr_json,
            uploaded_by=invoice.uploaded_by,
            created_at=invoice.created_at,
        )
        self.session.add(db_invoice)
        await self.session.flush()

        for item in invoice.line_items:
            db_item = LineItemDB(
                invoice_id=db_invoice.id,
                item_name=item.item_name,
                spec_model=item.spec_model,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.amount,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
            )
            self.session.add(db_item)

        for anomaly in invoice.anomalies:
            db_anomaly = InvoiceAnomalyDB(
                invoice_id=db_invoice.id,
                severity=anomaly.severity,
                code=anomaly.code,
                message=anomaly.message,
                field_path=anomaly.field_path,
            )
            self.session.add(db_anomaly)

        await self.session.flush()
        return invoice

    async def find_invoices_by_no(self, invoice_no: str) -> List[InvoiceRecord]:
        stmt = (
            select(InvoiceDB)
            .where(InvoiceDB.invoice_no == invoice_no)
            .options(selectinload(InvoiceDB.line_items), selectinload(InvoiceDB.anomalies))
        )
        result = await self.session.execute(stmt)
        db_invoices = result.scalars().all()
        return [self._to_invoice_record(db_inv) for db_inv in db_invoices]

    async def list_invoices(
        self, filters: Dict[str, Optional[str]], page: int, page_size: int
    ) -> Tuple[List[InvoiceRecord], int]:
        stmt = select(InvoiceDB).options(selectinload(InvoiceDB.line_items), selectinload(InvoiceDB.anomalies))

        invoice_no_filter = filters.get("invoice_no")
        if invoice_no_filter:
            stmt = stmt.where(InvoiceDB.invoice_no.contains(invoice_no_filter))

        status_filter = filters.get("status")
        if status_filter:
            stmt = stmt.where(InvoiceDB.status == status_filter)

        uploaded_by = filters.get("uploaded_by")
        if uploaded_by:
            stmt = stmt.where(InvoiceDB.uploaded_by == uploaded_by)

        date_start = filters.get("date_start")
        if date_start:
            try:
                start_date = date.fromisoformat(date_start)
                stmt = stmt.where(InvoiceDB.invoice_date >= start_date)
            except ValueError:
                pass

        date_end = filters.get("date_end")
        if date_end:
            try:
                end_date = date.fromisoformat(date_end)
                stmt = stmt.where(InvoiceDB.invoice_date <= end_date)
            except ValueError:
                pass

        amount_min = filters.get("amount_min")
        if amount_min:
            try:
                stmt = stmt.where(InvoiceDB.grand_total >= Decimal(amount_min))
            except Exception:
                pass

        amount_max = filters.get("amount_max")
        if amount_max:
            try:
                stmt = stmt.where(InvoiceDB.grand_total <= Decimal(amount_max))
            except Exception:
                pass

        item_name = filters.get("item_name")
        if item_name:
            stmt = stmt.join(InvoiceDB.line_items).where(LineItemDB.item_name.ilike(f"%{item_name}%"))

        stmt = stmt.order_by(InvoiceDB.created_at.desc())

        count_stmt = select(InvoiceDB.id)
        for criterion in stmt.whereclause if stmt.whereclause is not None else []:
            count_stmt = count_stmt.where(criterion)
        count_result = await self.session.execute(count_stmt)
        total = len(count_result.all())

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        db_invoices = result.unique().scalars().all()
        records = [self._to_invoice_record(db_inv) for db_inv in db_invoices]
        return records, total

    async def get_invoice_by_no(self, invoice_no: str) -> Optional[InvoiceRecord]:
        stmt = (
            select(InvoiceDB)
            .where(InvoiceDB.invoice_no == invoice_no)
            .options(selectinload(InvoiceDB.line_items), selectinload(InvoiceDB.anomalies))
            .order_by(InvoiceDB.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        db_invoice = result.scalar_one_or_none()
        if not db_invoice:
            return None
        return self._to_invoice_record(db_invoice)

    def _to_invoice_record(self, db_invoice: InvoiceDB) -> InvoiceRecord:
        line_items = [
            InvoiceLineItem(
                item_name=item.item_name,
                spec_model=item.spec_model,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.amount,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
            )
            for item in db_invoice.line_items
        ]
        anomalies = [
            InvoiceAnomaly(
                severity=AnomalySeverity(anomaly.severity),
                code=anomaly.code,
                message=anomaly.message,
                field_path=anomaly.field_path,
            )
            for anomaly in db_invoice.anomalies
        ]
        return InvoiceRecord(
            id=db_invoice.id,
            invoice_no=db_invoice.invoice_no,
            invoice_type=db_invoice.invoice_type,
            invoice_date=db_invoice.invoice_date,
            buyer_name=db_invoice.buyer_name,
            buyer_tax_id=db_invoice.buyer_tax_id,
            seller_name=db_invoice.seller_name,
            seller_tax_id=db_invoice.seller_tax_id,
            total_amount=db_invoice.total_amount,
            total_tax=db_invoice.total_tax,
            grand_total=db_invoice.grand_total,
            status=InvoiceStatus(db_invoice.status),
            source_file_id=db_invoice.source_file_id,
            raw_ocr_text=db_invoice.raw_ocr_text,
            raw_ocr_json=db_invoice.raw_ocr_json,
            uploaded_by=db_invoice.uploaded_by,
            created_at=db_invoice.created_at,
            line_items=line_items,
            anomalies=anomalies,
        )

    async def get_next_file_id(self) -> int:
        stmt = select(FileAssetDB.id).order_by(FileAssetDB.id.desc()).limit(1)
        result = await self.session.execute(stmt)
        last_id = result.scalar_one_or_none()
        return (last_id or 0) + 1

    async def get_next_invoice_id(self) -> int:
        stmt = select(InvoiceDB.id).order_by(InvoiceDB.id.desc()).limit(1)
        result = await self.session.execute(stmt)
        last_id = result.scalar_one_or_none()
        return (last_id or 0) + 1
