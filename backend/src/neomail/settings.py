"""Service settings, read from ``NEOMAIL_*`` environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field maps to ``NEOMAIL_<FIELD>``."""

    model_config = SettingsConfigDict(env_prefix="NEOMAIL_", extra="ignore", frozen=True)

    environment: Literal["development", "test", "production"] = Field(
        default="development", description="Deployment environment name."
    )
    log_level: Literal["debug", "info", "warning", "error"] = Field(
        default="info", description="Log level for the service."
    )
    contracts_dir: Path | None = Field(
        default=None,
        description=(
            "Directory holding the contracts (types/, events/, actions/). "
            "Defaults to the repository's contracts/ when running from a checkout."
        ),
    )
    stream_interval_seconds: float = Field(
        default=0.5,
        ge=0,
        le=60,
        description="Delay between events on the example event stream.",
    )
    idempotency_ttl_seconds: int = Field(
        default=86_400,
        ge=86_400,
        description="How long action results are kept for Idempotency-Key replays (>= 24 h).",
    )


@lru_cache
def get_settings() -> Settings:
    """Settings from the process environment, read once."""
    return Settings()
