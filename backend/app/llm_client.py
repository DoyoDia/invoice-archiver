from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx


@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str


@dataclass(slots=True)
class LLMResponse:
    text: str
    raw: Dict[str, Any]


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        stop: Optional[Sequence[str]] = None,
        temperature: float = 0.7,
        min_p: float = 0.0,
        repeat_penalty: float = 1.05,
        top_k: int = 20,
        top_p: float = 0.8,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_options = {
            "temperature": temperature,
            "min_p": min_p,
            "repeat_penalty": repeat_penalty,
            "top_k": top_k,
            "top_p": top_p,
        }
        if stop:
            self.default_options["stop"] = list(stop)
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def generate(self, prompt: str, *, options: Optional[Dict[str, Any]] = None) -> LLMResponse:
        client = await self._get_client()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "options": {**self.default_options, **(options or {})},
            "stream": False,
        }
        url = f"{self.base_url}/api/generate"
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Ollama streaming API may return newline-delimited chunks;
        # if we get a dict, assume final aggregated payload.
        if isinstance(data, dict):
            output_text = data.get("response") or data.get("text")
            if not output_text and "message" in data:
                output_text = data["message"].get("content")
        else:
            output_text = None

        if not output_text:
            raise ValueError("LLM response missing text content")

        return LLMResponse(text=output_text.strip(), raw=data)

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
