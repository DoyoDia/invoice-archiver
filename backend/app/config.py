from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    """从环境变量加载的应用配置。"""

    max_file_mb: int = field(default_factory=lambda: int(os.getenv("MAX_FILE_MB", "50")))
    max_pages: int = field(default_factory=lambda: int(os.getenv("MAX_PAGES", "50")))
    amount_tolerance: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("AMOUNT_TOLERANCE", "0.01"))
    )
    allowed_tax_rates: List[Decimal] = field(
        default_factory=lambda: [
            Decimal(r) for r in os.getenv("ALLOWED_TAX_RATES", "0,1,3,6,9,13").split(",") if r
        ]
    )
    storage_root: str = field(default_factory=lambda: os.getenv("STORAGE_ROOT", "data"))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./data/invoices.db")
    )

    # LLM 兜底（默认关闭）：仅当 LLM_BASE_URL 非空时启用。
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "qwen3:14b"))
    llm_request_timeout: int = field(default_factory=lambda: int(os.getenv("LLM_REQUEST_TIMEOUT", "30")))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url.strip())


def load_settings() -> Settings:
    return Settings()
