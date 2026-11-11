from __future__ import annotations

from collections.abc import Generator
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def normalize_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    if parts.scheme == "postgres":
        parts = parts._replace(scheme="postgresql+psycopg")
    elif parts.scheme == "postgresql":
        parts = parts._replace(scheme="postgresql+psycopg")
    elif parts.scheme not in {"postgresql+psycopg", "sqlite", "sqlite+pysqlite"}:
        raise ValueError("DATABASE_URL must use PostgreSQL or SQLite for tests")
    return cast(str, urlunsplit(parts))


def build_engine(database_url: str | None) -> Engine:
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Set it to the PostgreSQL instance before starting WORLDWEAVE."
        )

    normalized_url = normalize_database_url(database_url)
    options: dict[str, object] = {"pool_pre_ping": True}
    if normalized_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if normalized_url.endswith(":memory:"):
            options["poolclass"] = StaticPool
    return create_engine(normalized_url, **options)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    factory: sessionmaker[Session] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        raise RuntimeError("Database is not initialized")

    with factory() as session:
        yield session
