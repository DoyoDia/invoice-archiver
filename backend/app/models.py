from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import List, Optional


class FileStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class InvoiceStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    DUPLICATE = "duplicate"
    CONFLICT_DUPLICATE = "conflict_duplicate"


class AnomalySeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass(slots=True)
class FileAsset:
    id: int
    filename: str
    content_hash: str
    size: int
    pages: Optional[int]
    stored_path: Path
    status: FileStatus
    error: Optional[str]
    uploaded_at: datetime
    uploader_id: str


@dataclass(slots=True)
class JobRecord:
    job_id: str
    file_id: int
    status: str
    step: Optional[str]
    progress: float
    error: Optional[str]
    retry_count: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


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
class InvoiceAnomaly:
    severity: AnomalySeverity
    code: str
    message: str
    field_path: Optional[str] = None


@dataclass(slots=True)
class InvoiceRecord:
    id: int
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
    raw_ocr_text: str
    raw_ocr_json: dict
    line_items: List[InvoiceLineItem] = field(default_factory=list)
    anomalies: List[InvoiceAnomaly] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    uploaded_by: str = "unknown"


@dataclass(slots=True)
class User:
    user_id: str
    username: str
    role: str

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_viewer(self) -> bool:
        return self.role in {"viewer", "admin"}

    def is_uploader(self) -> bool:
        return self.role in {"uploader", "admin"}
