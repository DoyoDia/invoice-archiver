from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JobItem(BaseModel):
    job_id: str
    file_id: int
    status: str


class JobQueryResponse(BaseModel):
    job_id: str
    status: str
    step: Optional[str]
    progress: float = Field(ge=0.0, le=1.0)
    error: Optional[str]
    retry_count: int
    created_at: datetime
    updated_at: datetime
    file_id: int


class AnomalySchema(BaseModel):
    severity: str
    code: str
    message: str
    field_path: Optional[str] = None


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
    anomaly_codes: List[str] = Field(default_factory=list)
    uploaded_at: datetime


class InvoiceListResponse(BaseModel):
    items: List[InvoiceListItem]
    page: int
    page_size: int
    total: int


class InvoiceEntity(BaseModel):
    invoice_no: str
    invoice_type: Optional[str]
    invoice_date: Optional[str]
    buyer: Optional[dict]
    seller: Optional[dict]
    totals: Optional[dict]
    status: str
    source_file_id: int
    created_at: datetime


class LineItemSchema(BaseModel):
    item_name: Optional[str]
    spec_model: Optional[str]
    quantity: Optional[str]
    unit_price: Optional[str]
    amount: Optional[str]
    tax_rate: Optional[str]
    tax_amount: Optional[str]


class InvoiceDetailResponse(BaseModel):
    invoice: InvoiceEntity
    line_items: List[LineItemSchema]
    anomalies: List[AnomalySchema]
    raw_ocr_json: dict


class UploadResponse(BaseModel):
    jobs: List[JobItem]


class ErrorResponse(BaseModel):
    error: dict
