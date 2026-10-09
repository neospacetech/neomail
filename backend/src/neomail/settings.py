"""Service settings, read from ``NEOMAIL_*`` environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    tenant: str = Field(
        default="local",
        pattern=r"^[a-z0-9][a-z0-9-]{0,62}$",
        description="Tenant name used in object references (neo://<tenant>/o/<ulid>).",
    )
    jmap_api_url: str | None = Field(
        default=None,
        description=(
            "JMAP API URL of the mail server (Stalwart serves it at /jmap). "
            "When unset, outgoing mail is kept in memory instead of submitted."
        ),
    )
    jmap_account_id: str | None = Field(default=None, description="JMAP account id to send as.")
    jmap_identity_id: str | None = Field(
        default=None, description="JMAP identity used for EmailSubmission."
    )
    jmap_sent_mailbox_id: str | None = Field(
        default=None, description="JMAP mailbox that stores submitted messages."
    )
    jmap_token: SecretStr | None = Field(
        default=None, description="Bearer token for the JMAP server."
    )
    stream_interval_seconds: float = Field(
        default=0.5,
        ge=0,
        le=60,
        description="How often the change stream checks for new changes when following.",
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
