from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.core.config import Settings
from backend.core.models import Base
from backend.main import create_app
from backend.modules.identity.service import _rate_limiter


class CsrfTestClient(TestClient):
    """TestClient that automatically mirrors the CSRF cookie into the header.

    Browser clients use the same mechanism via ``custom-fetch.ts``. Tests that
    intentionally exercise CSRF rejection can pass an explicit header or clear
    the cookie before the call.
    """

    def request(self, method, url, **kwargs):  # type: ignore[override]
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf_token = self.cookies.get("ww_csrf")
            if csrf_token:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("x-csrf-token", csrf_token)
                kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        registration_mode="bootstrap_only",
        cookie_secure=False,
        session_ttl_days=30,
        auth_rate_limit=100,
        auth_rate_window_seconds=60,
        collaboration_ticket_secret="test-collaboration-secret",
        collaboration_materialize_delay_ms=25,
        collaboration_idle_close_seconds=1,
        collaboration_snapshot_update_threshold=4,
        collaboration_snapshot_byte_threshold=100_000,
        collaboration_revision_interval_seconds=1,
    )
    _rate_limiter.clear()
    application = create_app(settings=settings, engine=engine)
    with CsrfTestClient(application) as test_client:
        yield test_client
    engine.dispose()


@pytest.fixture
def open_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        registration_mode="open",
        cookie_secure=False,
        session_ttl_days=30,
        auth_rate_limit=1000,
        auth_rate_window_seconds=60,
    )
    _rate_limiter.clear()
    application = create_app(settings=settings, engine=engine)
    with CsrfTestClient(application) as test_client:
        yield test_client
    engine.dispose()
