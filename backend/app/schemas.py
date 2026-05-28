from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class IngestResultItem(BaseModel):
    file_id: int
    invoice_no: Optional[str] = None
    status: str
    error: Optional[str] = None


class UploadResponse(BaseModel):
    results: List[IngestResultItem]


class InvoiceListItem(BaseModel):
    invoice_id: int
    invoice_no: str
    invoice_date: Optional[str]
    buyer_name: Optional[str]
    seller_name: Optional[str]
    total_amount: Optional[str]
    total_tax: Optional[str]
    grand_total: Optional[str]
    status: str
    source_file_id: int
    uploaded_at: datetime


class InvoiceListResponse(BaseModel):
    items: List[InvoiceListItem]
    page: int
    page_size: int
    total: int


class LineItemSchema(BaseModel):
    item_name: Optional[str]
    spec_model: Optional[str]
    quantity: Optional[str]
    unit_price: Optional[str]
    amount: Optional[str]
    tax_rate: Optional[str]
    tax_amount: Optional[str]


class InvoiceEntity(BaseModel):
    invoice_no: str
    invoice_type: Optional[str]
    invoice_date: Optional[str]
    buyer: Optional[dict]
    seller: Optional[dict]
    totals: Optional[dict]
    status: str
    notes: Optional[str]
    source_file_id: int
    created_at: datetime


class InvoiceDetailResponse(BaseModel):
    invoice: InvoiceEntity
    line_items: List[LineItemSchema]
    raw_json: dict
