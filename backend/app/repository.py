from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .database import FileAssetDB, InvoiceDB, LineItemDB, TagDB
from .models import (
    FileAsset,
    FileStatus,
    InvoiceLineItem,
    InvoiceRecord,
    InvoiceStatus,
)


def _line_item_db(item: InvoiceLineItem) -> LineItemDB:
    return LineItemDB(
        item_name=item.item_name,
        spec_model=item.spec_model,
        quantity=item.quantity,
        unit_price=item.unit_price,
        amount=item.amount,
        tax_rate=item.tax_rate,
        tax_amount=item.tax_amount,
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
            deleted=invoice.deleted,
            source_file_id=invoice.source_file_id,
            raw_text=invoice.raw_text,
            raw_json=invoice.raw_json,
            created_at=invoice.created_at,
            line_items=[_line_item_db(item) for item in invoice.line_items],
            tags=self._get_or_create_tags(invoice.tags),
        )
        self.session.add(db_invoice)
        self.session.flush()
        invoice.id = db_invoice.id
        return invoice

    def revive_if_deleted(self, invoice: InvoiceRecord) -> Optional[InvoiceRecord]:
        """同号且已标记删除的记录：用新解析结果更新并取消删除标记，避免重复。"""
        stmt = (
            select(InvoiceDB)
            .where(InvoiceDB.invoice_no == invoice.invoice_no, InvoiceDB.deleted.is_(True))
            .options(selectinload(InvoiceDB.line_items), selectinload(InvoiceDB.tags))
            .order_by(InvoiceDB.created_at.desc())
            .limit(1)
        )
        db = self.session.execute(stmt).scalar_one_or_none()
        if db is None:
            return None
        db.invoice_type = invoice.invoice_type
        db.invoice_date = invoice.invoice_date
        db.buyer_name, db.buyer_tax_id = invoice.buyer_name, invoice.buyer_tax_id
        db.seller_name, db.seller_tax_id = invoice.seller_name, invoice.seller_tax_id
        db.total_amount, db.total_tax, db.grand_total = invoice.total_amount, invoice.total_tax, invoice.grand_total
        db.status, db.notes = invoice.status.value, invoice.notes
        db.deleted = False
        db.source_file_id = invoice.source_file_id
        db.raw_text, db.raw_json = invoice.raw_text, invoice.raw_json
        db.created_at = invoice.created_at  # 重新上传：刷新上传时间
        db.line_items = [_line_item_db(item) for item in invoice.line_items]
        if invoice.tags:
            existing = {t.name for t in db.tags}
            db.tags.extend(t for t in self._get_or_create_tags(invoice.tags) if t.name not in existing)
        self.session.flush()
        return self._to_record(db)

    def count_active_by_invoice_no(self, invoice_no: str) -> int:
        stmt = (
            select(func.count())
            .select_from(InvoiceDB)
            .where(InvoiceDB.invoice_no == invoice_no, InvoiceDB.deleted.is_(False))
        )
        return self.session.execute(stmt).scalar_one()

    # --- 标签 ---

    def _get_or_create_tags(self, names: List[str]) -> List[TagDB]:
        tags: List[TagDB] = []
        seen = set()
        for raw in names:
            name = raw.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            tag = self.session.execute(select(TagDB).where(TagDB.name == name)).scalar_one_or_none()
            if tag is None:
                tag = TagDB(name=name)
                self.session.add(tag)
                self.session.flush()
            tags.append(tag)
        return tags

    def list_tags(self, q: Optional[str] = None) -> List[Tuple[int, str]]:
        stmt = select(TagDB.id, TagDB.name)
        if q:
            stmt = stmt.where(TagDB.name.contains(q))
        return list(self.session.execute(stmt.order_by(TagDB.name)).all())

    def create_tag(self, name: str) -> Tuple[int, str]:
        tag = self._get_or_create_tags([name])[0]
        return tag.id, tag.name

    def delete_tag(self, tag_id: int) -> bool:
        tag = self.session.get(TagDB, tag_id)
        if tag is None:
            return False
        self.session.delete(tag)  # 关联表 invoice_tags 由级联清理
        return True

    def set_invoice_tags(self, invoice_no: str, names: List[str]) -> Optional[InvoiceRecord]:
        db = self._latest_db(invoice_no, with_tags=True)
        if db is None:
            return None
        db.tags = self._get_or_create_tags(names)
        self.session.flush()
        return self._to_record(db)

    def set_deleted(self, invoice_no: str, deleted: bool) -> Optional[InvoiceRecord]:
        db = self._latest_db(invoice_no, with_tags=True)
        if db is None:
            return None
        db.deleted = deleted
        self.session.flush()
        return self._to_record(db)

    def _latest_db(self, invoice_no: str, with_tags: bool = False) -> Optional[InvoiceDB]:
        opts = [selectinload(InvoiceDB.line_items)]
        if with_tags:
            opts.append(selectinload(InvoiceDB.tags))
        stmt = (
            select(InvoiceDB)
            .where(InvoiceDB.invoice_no == invoice_no)
            .options(*opts)
            .order_by(InvoiceDB.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_invoices(
        self, filters: Dict[str, Optional[str]], page: int, page_size: int, include_deleted: bool = True
    ) -> Tuple[List[InvoiceRecord], int]:
        stmt = select(InvoiceDB).options(selectinload(InvoiceDB.line_items), selectinload(InvoiceDB.tags))

        if not include_deleted:
            stmt = stmt.where(InvoiceDB.deleted.is_(False))
        if filters.get("invoice_no"):
            stmt = stmt.where(InvoiceDB.invoice_no.contains(filters["invoice_no"]))
        if filters.get("status"):
            statuses = [s for s in filters["status"].split(",") if s]
            stmt = stmt.where(InvoiceDB.status.in_(statuses) if len(statuses) > 1 else InvoiceDB.status == statuses[0])
        if filters.get("tag"):
            stmt = stmt.where(InvoiceDB.tags.any(TagDB.name == filters["tag"]))
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
        db_invoice = self._latest_db(invoice_no, with_tags=True)
        return self._to_record(db_invoice) if db_invoice else None

    def status_counts(self) -> Dict[str, int]:
        stmt = (
            select(InvoiceDB.status, func.count())
            .where(InvoiceDB.deleted.is_(False))
            .group_by(InvoiceDB.status)
        )
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
            deleted=db_invoice.deleted,
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
            tags=[t.name for t in db_invoice.tags],
        )
