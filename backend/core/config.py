from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    registration_mode: str = "bootstrap_only"
    cookie_secure: bool = True
    session_ttl_days: int = 30
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60

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

        return cls(
            database_url=os.getenv("DATABASE_URL"),
            registration_mode=mode,
            cookie_secure=cookie_secure,
            session_ttl_days=int(os.getenv("SESSION_TTL_DAYS", "30")),
            auth_rate_limit=int(os.getenv("AUTH_RATE_LIMIT", "10")),
            auth_rate_window_seconds=int(
                os.getenv("AUTH_RATE_WINDOW_SECONDS", "60")
            ),
        )
