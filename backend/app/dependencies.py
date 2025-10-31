from __future__ import annotations

from fastapi import Depends, Request

from .config import Settings
from .service import InvoiceService
from .state import InMemoryStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> InMemoryStore:
    return request.app.state.store


def get_service(request: Request) -> InvoiceService:
    return request.app.state.service
