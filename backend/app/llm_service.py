from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import pymupdf4llm

from .config import Settings
from .llm_client import LLMClient


INVOICE_PROMPT_TEMPLATE = """You are an information extraction assistant. Convert the noisy OCR text of a Chinese electronic VAT normal invoice (电子发票（普通发票）) into a SINGLE JSON object using the EXACT Chinese keys and schema below. \
Do not add extra keys. If a field is missing or uncertain, set it to null. \
Return ONLY the JSON (no explanations, no markdown).\n\nSOURCE TEXT (raw OCR; do not ignore any line):\n<<<\n{source_text}\n>>>\n\nREPAIR RULES (before extracting):\n- Merge per-character vertical lines into words (e.g., "购\n买\n方\n信\n息" → "购买方信息", "销\n售\n方\n信\n息" → "销售方信息").\n- Join "Field:\nValue" into a single logical field line.\n- Normalize whitespace, unify colons, keep all digits of IDs.\n- Keep Chinese date format as-is (YYYY年MM月DD日).\n\nSCHEMA (keys MUST be these exact Chinese names; absent values → null):\n{{\n  "发票类型": "电子发票（普通发票）",\n  "发票号码": string|null,\n  "开票日期": string|null,                // keep Chinese date like "2025年06月20日"\n  "购买方信息": {{ "名称": string|null, "纳税人识别号": string|null }},\n  "销售方信息": {{ "名称": string|null, "纳税人识别号": string|null }},\n  "项目": [                                // array of detail rows (0..n)\n    {{\n      "项目名称": string|null,\n      "规格型号": string|null,\n      "单位": string|null,\n      "数量": string|null,\n      "单价": string|null,\n      "金额": string|null,\n      "税率": string|null,                 // keep as original string like "1%"\n      "税额": string|null\n    }}\n  ],\n  "合计": {{ "金额": string|null, "税额": string|null }},\n  "价税合计": {{ "大写": string|null, "小写": string|null }},\n  "备注": string|null,\n  "开票人": string|null\n}}\n\nNORMALIZATION FOR VALUES:\n- For numeric-like fields, keep them as strings to avoid precision loss (e.g., "128.71").\n- Remove currency symbols in numeric strings (e.g., "¥130.00" → "130.00").\n- Keep percentage strings as-is (e.g., "1%").\n- For missing/uncertain fields, use null (not empty string), unless the value clearly exists but is empty by design.\n\nASSIGNMENT HINTS:\n- Distinguish buyer vs seller by nearest section header（“购买方信息” vs “销售方信息”）。\n- Prefer the clearer occurrence if duplicates appear.\n- For 项目 rows, if “规格型号/单位/数量/单价/金额/税率/税额” appear scattered, align them by proximity and semantics.\n\nOUTPUT:\n- Return ONLY one JSON object, exactly following the schema and key order above.\n"""


@dataclass(slots=True)
class LLMParseResult:
    data: dict
    source_markdown: str
    raw_response: dict


@dataclass(slots=True)
class LLMService:
    settings: Settings
    llm_client: LLMClient

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMService":
        stop_tokens = tuple(settings.llm_stop_tokens) if settings.llm_stop_tokens else None
        llm_client = LLMClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            stop=stop_tokens,
            temperature=settings.llm_temperature,
            min_p=settings.llm_min_p,
            repeat_penalty=settings.llm_repeat_penalty,
            top_k=settings.llm_top_k,
            top_p=settings.llm_top_p,
            timeout=float(settings.llm_request_timeout),
        )
        return cls(settings=settings, llm_client=llm_client)

    async def parse_invoice(self, pdf_path: Path) -> LLMParseResult:
        markdown_text = pymupdf4llm.to_markdown(str(pdf_path))
        prompt = INVOICE_PROMPT_TEMPLATE.format(source_text=markdown_text)
        response = await self.llm_client.generate(prompt)

        try:
            parsed = json.loads(response.text)
            if not isinstance(parsed, dict):
                raise ValueError("LLM did not return a JSON object")
            return LLMParseResult(data=parsed, source_markdown=markdown_text, raw_response=response.raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to decode LLM JSON response: {exc}") from exc

    async def aclose(self) -> None:
        await self.llm_client.aclose()
