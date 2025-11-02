from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .models import AnomalySeverity, FileStatus, InvoiceStatus


class Base(AsyncAttrs, DeclarativeBase):
    pass


class FileAssetDB(Base):
    __tablename__ = "file_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(FileStatus, name="file_status_enum", create_constraint=True),
        nullable=False,
        default=FileStatus.QUEUED,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    uploader_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    invoices: Mapped[List["InvoiceDB"]] = relationship("InvoiceDB", back_populates="source_file")


class InvoiceDB(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    invoice_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    buyer_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    buyer_tax_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_tax_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    total_tax: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    grand_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status_enum", create_constraint=True),
        nullable=False,
        default=InvoiceStatus.OK,
        index=True,
    )
    source_file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("file_assets.id", ondelete="CASCADE"), nullable=False
    )
    raw_ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_ocr_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    uploaded_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True, default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    source_file: Mapped["FileAssetDB"] = relationship("FileAssetDB", back_populates="invoices")
    line_items: Mapped[List["LineItemDB"]] = relationship(
        "LineItemDB", back_populates="invoice", cascade="all, delete-orphan"
    )
    anomalies: Mapped[List["InvoiceAnomalyDB"]] = relationship(
        "InvoiceAnomalyDB", back_populates="invoice", cascade="all, delete-orphan"
    )


class LineItemDB(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spec_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)

    invoice: Mapped["InvoiceDB"] = relationship("InvoiceDB", back_populates="line_items")


class InvoiceAnomalyDB(Base):
    __tablename__ = "invoice_anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(
        Enum(AnomalySeverity, name="anomaly_severity_enum", create_constraint=True), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    field_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    invoice: Mapped["InvoiceDB"] = relationship("InvoiceDB", back_populates="anomalies")


class JobRecordDB(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    step: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    progress: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP")
    )


def create_engine_from_url(database_url: str):
    return create_async_engine(database_url, echo=False, future=True)


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
