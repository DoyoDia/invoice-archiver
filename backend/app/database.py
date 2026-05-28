from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class FileAssetDB(Base):
    __tablename__ = "file_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processed")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    invoices: Mapped[List["InvoiceDB"]] = relationship(back_populates="source_file")


class InvoiceDB(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_no: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    invoice_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    buyer_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    buyer_tax_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_tax_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    total_tax: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    grand_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("file_assets.id", ondelete="CASCADE"), nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    source_file: Mapped["FileAssetDB"] = relationship(back_populates="invoices")
    line_items: Mapped[List["LineItemDB"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
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

    invoice: Mapped["InvoiceDB"] = relationship(back_populates="line_items")


def create_db_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, echo=False, future=True, connect_args=connect_args)


def create_session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
