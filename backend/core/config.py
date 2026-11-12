from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    registration_mode: str = "bootstrap_only"
    cookie_secure: bool = True
    session_ttl_days: int = 30
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60
    collaboration_ticket_secret: str = ""
    collaboration_ticket_ttl_seconds: int = 120
    collaboration_snapshot_update_threshold: int = 64
    collaboration_snapshot_byte_threshold: int = 1_048_576
    collaboration_revision_interval_seconds: int = 600
    collaboration_materialize_delay_ms: int = 1500
    collaboration_idle_close_seconds: int = 30
    media_root: str = "var/media"
    max_asset_bytes: int = 10_485_760

    @classmethod
    def from_env(cls) -> Settings:
        mode = os.getenv("REGISTRATION_MODE", "bootstrap_only").strip().lower()
        if mode not in {"bootstrap_only", "open", "closed"}:
            raise ValueError(
                "REGISTRATION_MODE must be bootstrap_only, open, or closed"
            )

        secure_setting = os.getenv("COOKIE_SECURE")
        cookie_secure = (
            secure_setting.strip().lower() in {"1", "true", "yes", "on"}
            if secure_setting is not None
            else os.getenv("ENVIRONMENT", "production").lower() != "development"
        )

        ticket_secret = os.getenv("COLLABORATION_TICKET_SECRET", "").strip()
        if not ticket_secret:
            # A per-process secret keeps development and single-worker
            # deployments safe. Multi-worker deployments must configure the
            # environment variable so tickets validate across processes.
            ticket_secret = secrets.token_urlsafe(48)

        return cls(
            database_url=os.getenv("DATABASE_URL"),
            registration_mode=mode,
            cookie_secure=cookie_secure,
            session_ttl_days=int(os.getenv("SESSION_TTL_DAYS", "30")),
            auth_rate_limit=int(os.getenv("AUTH_RATE_LIMIT", "10")),
            auth_rate_window_seconds=int(
                os.getenv("AUTH_RATE_WINDOW_SECONDS", "60")
            ),
            collaboration_ticket_secret=ticket_secret,
            collaboration_ticket_ttl_seconds=_positive_int(
                "COLLABORATION_TICKET_TTL_SECONDS", 120
            ),
            collaboration_snapshot_update_threshold=_positive_int(
                "COLLABORATION_SNAPSHOT_UPDATE_THRESHOLD", 64
            ),
            collaboration_snapshot_byte_threshold=_positive_int(
                "COLLABORATION_SNAPSHOT_BYTE_THRESHOLD", 1_048_576
            ),
            collaboration_revision_interval_seconds=_positive_int(
                "COLLABORATION_REVISION_INTERVAL_SECONDS", 600
            ),
            collaboration_materialize_delay_ms=_positive_int(
                "COLLABORATION_MATERIALIZE_DELAY_MS", 1500
            ),
            collaboration_idle_close_seconds=_positive_int(
                "COLLABORATION_IDLE_CLOSE_SECONDS", 30
            ),
            media_root=os.getenv("MEDIA_ROOT", "var/media").strip() or "var/media",
            max_asset_bytes=_positive_int(
                "MAX_ASSET_BYTES", 10_485_760
            ),
        )
