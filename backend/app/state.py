from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Dict, List, Optional

from .models import FileAsset, InvoiceRecord, JobRecord


@dataclass(slots=True)
class InMemoryStore:
    file_assets: Dict[int, FileAsset] = field(default_factory=dict)
    invoices: Dict[int, InvoiceRecord] = field(default_factory=dict)
    jobs: Dict[str, JobRecord] = field(default_factory=dict)
    invoice_index: Dict[str, List[int]] = field(default_factory=dict)
    file_seq: int = 0
    invoice_seq: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    job_events: Dict[str, asyncio.Event] = field(default_factory=dict)
    processing_queue: Deque[str] = field(default_factory=deque)

    async def next_file_id(self) -> int:
        async with self.lock:
            self.file_seq += 1
            return self.file_seq

    async def next_invoice_id(self) -> int:
        async with self.lock:
            self.invoice_seq += 1
            return self.invoice_seq

    async def register_file(self, asset: FileAsset) -> None:
        async with self.lock:
            self.file_assets[asset.id] = asset

    async def register_job(self, job: JobRecord) -> None:
        async with self.lock:
            self.jobs[job.job_id] = job
            self.job_events[job.job_id] = asyncio.Event()
            self.processing_queue.append(job.job_id)

    async def update_job(self, job: JobRecord) -> None:
        async with self.lock:
            self.jobs[job.job_id] = job
            event = self.job_events.get(job.job_id)
        if event:
            event.set()

    async def update_file(self, asset: FileAsset) -> None:
        async with self.lock:
            self.file_assets[asset.id] = asset

    async def record_invoice(self, invoice: InvoiceRecord) -> None:
        async with self.lock:
            self.invoices[invoice.id] = invoice
            self.invoice_index.setdefault(invoice.invoice_no, []).append(invoice.id)

    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        async with self.lock:
            return self.jobs.get(job_id)

    async def get_file(self, file_id: int) -> Optional[FileAsset]:
        async with self.lock:
            return self.file_assets.get(file_id)

    async def list_invoices(self) -> List[InvoiceRecord]:
        async with self.lock:
            return list(self.invoices.values())

    async def find_by_invoice_no(self, invoice_no: str) -> List[InvoiceRecord]:
        async with self.lock:
            ids = self.invoice_index.get(invoice_no, [])
            return [self.invoices[i] for i in ids]


def ensure_storage_dirs(root: Path) -> None:
    invoices_dir = root / "invoices"
    invoices_dir.mkdir(parents=True, exist_ok=True)
    (root / "tmp").mkdir(parents=True, exist_ok=True)
