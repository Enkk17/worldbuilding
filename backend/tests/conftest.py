from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.core.config import Settings
from backend.core.models import Base
from backend.main import create_app
from backend.modules.identity.service import _rate_limiter


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
    )
    _rate_limiter.clear()
    application = create_app(settings=settings, engine=engine)
    with TestClient(application) as test_client:
        yield test_client
    engine.dispose()
