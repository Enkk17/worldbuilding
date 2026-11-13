"""Seed a small dataset into PostgreSQL for the M9 backup/restore drill.

Run with DATABASE_URL pointing at the target database. It exercises the real
service layer (not raw SQL) so the dump captures representative rows.
"""

from __future__ import annotations

import json
import os
import uuid

from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.core.database import build_engine
from backend.main import create_app
from backend.tests.conftest import CsrfTestClient

DATABASE_URL = os.environ["DATABASE_URL"]
PASSWORD = "password123456"
AUTH_HEADERS = {"Origin": "http://testserver"}


def main() -> None:
    engine = build_engine(DATABASE_URL)
    settings = Settings(
        database_url=DATABASE_URL,
        registration_mode="open",
        cookie_secure=False,
        collaboration_ticket_secret="drill-secret",
    )
    app = create_app(settings=settings, engine=engine)
    with CsrfTestClient(app) as client:
        client.cookies.clear()
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": "drill-owner@example.com",
                "display_name": "Drill Owner",
                "password": PASSWORD,
            },
            headers=AUTH_HEADERS,
        )
        assert register.status_code in {201, 409}, register.text
        if register.status_code == 409:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "drill-owner@example.com", "password": PASSWORD},
                headers=AUTH_HEADERS,
            )
            assert login.status_code == 200, login.text

        universe = client.post(
            "/api/v1/universes", json={"name": "Drill Realm"}
        )
        assert universe.status_code == 201, universe.text
        universe_id = universe.json()["id"]

        for title in ("Drill Hero", "Drill Harbour", "Drill Relic"):
            created = client.post(
                f"/api/v1/universes/{universe_id}/entities",
                json={"entity_type_key": "character", "title": title},
            )
            assert created.status_code == 201, created.text

        document = client.post(
            f"/api/v1/universes/{universe_id}/documents",
            json={
                "title": "Drill Chapter",
                "content_json": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Restored content."}],
                        }
                    ],
                },
            },
        )
        assert document.status_code == 201, document.text

        entities = client.get(f"/api/v1/universes/{universe_id}/entities").json()
        print(
            json.dumps(
                {
                    "universe_id": universe_id,
                    "entities": entities["total"],
                    "documents": client.get(
                        f"/api/v1/universes/{universe_id}/documents"
                    ).json()["total"],
                }
            )
        )
    engine.dispose()


if __name__ == "__main__":
    main()
