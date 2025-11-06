from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default)
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    """Application configuration loaded from environment variables."""

    max_file_mb: int = field(default_factory=lambda: int(os.getenv("MAX_FILE_MB", "100")))
    max_pages: int = field(default_factory=lambda: int(os.getenv("MAX_PAGES", "100")))
    amount_tolerance: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("AMOUNT_TOLERANCE", "0.01"))
    )
    allowed_tax_rates: List[Decimal] = field(
        default_factory=lambda: [Decimal(rate) for rate in os.getenv("ALLOWED_TAX_RATES", "0,1,3,6,9,13").split(",") if rate]
    )
    storage_root: str = field(default_factory=lambda: os.getenv("STORAGE_ROOT", "data"))
    ocr_base_url: str = field(default_factory=lambda: os.getenv("OCR_BASE_URL", "http://100.98.65.26:3000"))
    ocr_endpoint: str = field(default_factory=lambda: os.getenv("OCR_ENDPOINT", "/api/ocr-pdf"))
    ocr_mode: str = field(default_factory=lambda: os.getenv("OCR_MODE", "plain_ocr"))
    ocr_prompt: str = field(default_factory=lambda: os.getenv("OCR_PROMPT", "Output in JSON format"))
    ocr_request_timeout: int = field(default_factory=lambda: int(os.getenv("OCR_REQUEST_TIMEOUT", "120")))
    ocr_retry_max: int = field(default_factory=lambda: int(os.getenv("OCR_RETRY_MAX", "2")))
    timezone: str = field(default_factory=lambda: os.getenv("TZ", "Asia/Shanghai"))
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://invoice:ZdydYYd3tRNyMZcC@100.98.65.26:5432/invoice",
        )
    )
    demo_tokens: dict[str, str] = field(
        default_factory=lambda: {
            os.getenv("DEMO_UPLOADER_TOKEN", "uploader-token"): "uploader",
            os.getenv("DEMO_VIEWER_TOKEN", "viewer-token"): "viewer",
            os.getenv("DEMO_ADMIN_TOKEN", "admin-token"): "admin",
        }
    )
    llm_enabled: bool = field(default_factory=lambda: _env_bool("LLM_ENABLED", "true"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://100.98.65.26:11434"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "Qwen3-30B-A3B-Instruct-2507"))
    llm_temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.7")))
    llm_min_p: float = field(default_factory=lambda: float(os.getenv("LLM_MIN_P", "0.0")))
    llm_repeat_penalty: float = field(default_factory=lambda: float(os.getenv("LLM_REPEAT_PENALTY", "1.05")))
    llm_top_k: int = field(default_factory=lambda: int(os.getenv("LLM_TOP_K", "20")))
    llm_top_p: float = field(default_factory=lambda: float(os.getenv("LLM_TOP_P", "0.8")))
    llm_stop_tokens: List[str] = field(
        default_factory=lambda: [token for token in os.getenv("LLM_STOP_TOKENS", "<|im_start|>,<|im_end|>").split(",") if token]
    )
    llm_request_timeout: int = field(default_factory=lambda: int(os.getenv("LLM_REQUEST_TIMEOUT", "120")))


def load_settings() -> Settings:
    return Settings()
