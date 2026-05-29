from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import List, Optional


class FileStatus(str, Enum):
    PROCESSED = "processed"
    FAILED = "failed"


class InvoiceStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    DUPLICATE = "duplicate"


@dataclass(slots=True)
class FileAsset:
    id: Optional[int]
    filename: str
    content_hash: str
    size: int
    pages: Optional[int]
    stored_path: Path
    status: FileStatus
    error: Optional[str]
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class InvoiceLineItem:
    item_name: Optional[str]
    spec_model: Optional[str]
    quantity: Optional[Decimal]
    unit_price: Optional[Decimal]
    amount: Optional[Decimal]
    tax_rate: Optional[Decimal]
    tax_amount: Optional[Decimal]


@dataclass(slots=True)
class InvoiceRecord:
    id: Optional[int]
    invoice_no: str
    invoice_type: Optional[str]
    invoice_date: Optional[date]
    buyer_name: Optional[str]
    buyer_tax_id: Optional[str]
    seller_name: Optional[str]
    seller_tax_id: Optional[str]
    total_amount: Optional[Decimal]
    total_tax: Optional[Decimal]
    grand_total: Optional[Decimal]
    status: InvoiceStatus
    source_file_id: int
    raw_text: str
    raw_json: dict
    notes: Optional[str] = None
    deleted: bool = False
    line_items: List[InvoiceLineItem] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
