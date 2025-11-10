from __future__ import annotations

from fastapi import Request

from .config import Settings
from .service_db import InvoiceServiceDB


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_service(request: Request) -> InvoiceServiceDB:
    return request.app.state.service
