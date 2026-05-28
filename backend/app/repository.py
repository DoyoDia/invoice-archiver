from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .database import FileAssetDB, InvoiceDB, LineItemDB
from .models import (
    FileAsset,
    FileStatus,
    InvoiceLineItem,
    InvoiceRecord,
    InvoiceStatus,
)


class InvoiceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_file_asset(self, asset: FileAsset) -> FileAsset:
        db_asset = FileAssetDB(
            filename=asset.filename,
            content_hash=asset.content_hash,
            size=asset.size,
            pages=asset.pages,
            stored_path=str(asset.stored_path),
            status=asset.status.value,
            error=asset.error,
        )
        self.session.add(db_asset)
        self.session.flush()
        asset.id = db_asset.id
        return asset

    def set_stored_path(self, file_id: int, path: str) -> None:
        db_asset = self.session.get(FileAssetDB, file_id)
        if db_asset:
            db_asset.stored_path = path

    def mark_failed(self, file_id: int, error: str) -> None:
        db_asset = self.session.get(FileAssetDB, file_id)
        if db_asset:
            db_asset.status = FileStatus.FAILED.value
            db_asset.error = error

    def get_file_asset(self, file_id: int) -> Optional[FileAsset]:
        db_asset = self.session.get(FileAssetDB, file_id)
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
        )

    def create_invoice(self, invoice: InvoiceRecord) -> InvoiceRecord:
        db_invoice = InvoiceDB(
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
            status=invoice.status.value,
            notes=invoice.notes,
            source_file_id=invoice.source_file_id,
            raw_text=invoice.raw_text,
            raw_json=invoice.raw_json,
            line_items=[
                LineItemDB(
                    item_name=item.item_name,
                    spec_model=item.spec_model,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    amount=item.amount,
                    tax_rate=item.tax_rate,
                    tax_amount=item.tax_amount,
                )
                for item in invoice.line_items
            ],
        )
        self.session.add(db_invoice)
        self.session.flush()
        invoice.id = db_invoice.id
        return invoice

    def count_by_invoice_no(self, invoice_no: str) -> int:
        stmt = select(func.count()).select_from(InvoiceDB).where(InvoiceDB.invoice_no == invoice_no)
        return self.session.execute(stmt).scalar_one()

    def list_invoices(
        self, filters: Dict[str, Optional[str]], page: int, page_size: int
    ) -> Tuple[List[InvoiceRecord], int]:
        stmt = select(InvoiceDB).options(selectinload(InvoiceDB.line_items))

        if filters.get("invoice_no"):
            stmt = stmt.where(InvoiceDB.invoice_no.contains(filters["invoice_no"]))
        if filters.get("status"):
            stmt = stmt.where(InvoiceDB.status == filters["status"])
        if filters.get("date_start"):
            try:
                stmt = stmt.where(InvoiceDB.invoice_date >= date.fromisoformat(filters["date_start"]))
            except ValueError:
                pass
        if filters.get("date_end"):
            try:
                stmt = stmt.where(InvoiceDB.invoice_date <= date.fromisoformat(filters["date_end"]))
            except ValueError:
                pass

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.session.execute(count_stmt).scalar_one()

        stmt = stmt.order_by(InvoiceDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        records = [self._to_record(r) for r in self.session.execute(stmt).scalars().unique().all()]
        return records, total

    def get_invoice_by_no(self, invoice_no: str) -> Optional[InvoiceRecord]:
        stmt = (
            select(InvoiceDB)
            .where(InvoiceDB.invoice_no == invoice_no)
            .options(selectinload(InvoiceDB.line_items))
            .order_by(InvoiceDB.created_at.desc())
            .limit(1)
        )
        db_invoice = self.session.execute(stmt).scalar_one_or_none()
        return self._to_record(db_invoice) if db_invoice else None

    def status_counts(self) -> Dict[str, int]:
        stmt = select(InvoiceDB.status, func.count()).group_by(InvoiceDB.status)
        counts = {status: count for status, count in self.session.execute(stmt).all()}
        counts["total"] = sum(counts.values())
        return counts

    def _to_record(self, db_invoice: InvoiceDB) -> InvoiceRecord:
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
            notes=db_invoice.notes,
            source_file_id=db_invoice.source_file_id,
            raw_text=db_invoice.raw_text,
            raw_json=db_invoice.raw_json,
            created_at=db_invoice.created_at,
            line_items=[
                InvoiceLineItem(
                    item_name=i.item_name,
                    spec_model=i.spec_model,
                    quantity=i.quantity,
                    unit_price=i.unit_price,
                    amount=i.amount,
                    tax_rate=i.tax_rate,
                    tax_amount=i.tax_amount,
                )
                for i in db_invoice.line_items
            ],
        )
