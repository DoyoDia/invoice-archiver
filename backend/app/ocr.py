from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .config import Settings


@dataclass(slots=True)
class OcrResult:
    text: str
    raw_response: Dict[str, Any]


class OCRClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=self.settings.ocr_request_timeout)
            return self._client

    async def recognize_pdf(self, file_path: Path) -> OcrResult:
        client = await self._get_client()
        url = f"{self.settings.ocr_base_url.rstrip('/')}/{self.settings.ocr_endpoint.lstrip('/')}"

        data = {
            "mode": self.settings.ocr_mode,
            "prompt": self.settings.ocr_prompt,
            "grounding": "false",
            "include_caption": "false",
            "find_term": "",
            "schema": "",
            "base_size": "1024",
            "image_size": "640",
            "crop_mode": "true",
            "test_compress": "false",
            "dpi": "144",
        }

        with file_path.open("rb") as fp:
            files = {"file": (file_path.name, fp, "application/pdf")}
            response = await client.post(url, files=files, data=data)
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            text = payload.get("text") or payload.get("result")
            if not text and "data" in payload:
                text = payload["data"].get("text") if isinstance(payload["data"], dict) else None
        else:
            text = None

        if not text:
            raise ValueError("OCR response missing text content")

        return OcrResult(text=text, raw_response=payload if isinstance(payload, dict) else {"raw": payload})

    async def aclose(self) -> None:
        async with self._lock:
            if self._client:
                await self._client.aclose()
                self._client = None
