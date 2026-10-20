"""Settings, read from environment variables (or a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    reasoning_effort: str = os.getenv("GROQ_REASONING_EFFORT", "low")  # gpt-oss: low | medium | high
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    data_dir: Path = Path(os.getenv("DAFA_DATA_DIR", BACKEND_DIR / "data" / "processed"))
    raw_dir: Path = BACKEND_DIR / "data" / "raw"
    top_k: int = int(os.getenv("DAFA_TOP_K", "6"))
    rate_limit_per_min: int = int(os.getenv("DAFA_RATE_LIMIT", "12"))
    allowed_origins: list[str] = field(default_factory=_origins)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.groq_api_key)


settings = Settings()
