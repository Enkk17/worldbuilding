"""Release security audit: the mandatory checks in TEST_STRATEGY section 2.

These are integration tests against the real application (no mocks). They
complement the per-milestone suites by asserting the cross-cutting security
properties that a release must demonstrate, including the leak-resistance of
the newer search, graph, and import/export surfaces.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from backend.core.config import Settings
from backend.core.models import Base
from backend.main import create_app
from backend.modules.exports.bundle import render_checksums
from backend.modules.identity.service import _rate_limiter
from backend.tests.conftest import CsrfTestClient

AUTH_HEADERS = {"Origin": "http://testserver"}
PASSWORD = "password123456"


@pytest.fixture
def client(tmp_path):
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
        collaboration_ticket_secret="test-collaboration-secret",
        collaboration_materialize_delay_ms=25,
        collaboration_idle_close_seconds=1,
        collaboration_snapshot_update_threshold=4,
        collaboration_snapshot_byte_threshold=100_000,
        collaboration_revision_interval_seconds=1,
        media_root=str(tmp_path / "media"),
        max_asset_bytes=1_048_576,
    )
    _rate_limiter.clear()
    application = create_app(settings=settings, engine=engine)
    with CsrfTestClient(application) as test_client:
        yield test_client
    engine.dispose()


def register(client: TestClient, email: str) -> dict:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": email.split("@")[0], "password": PASSWORD},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str) -> None:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text


def create_universe(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/universes", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def invite_and_accept(client: TestClient, universe_id: str, owner: str, email: str, role: str) -> dict:
    login(client, owner)
    invitation = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": email, "role": role},
    )
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()["invitation_token"]
    member = register(client, email)
    accepted = client.post(f"/api/v1/invitations/{token}/accept")
    assert accepted.status_code == 200, accepted.text
    login(client, owner)
    return member


def create_entity(client: TestClient, universe_id: str, title: str, **extra) -> dict:
    response = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "character", "title": title, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


# -----------------------------------------------------------------------------
# Authentication and session
# -----------------------------------------------------------------------------

def test_unauthenticated_api_access_is_rejected(client: TestClient):
    client.cookies.clear()
    assert client.get("/api/v1/universes").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    # A well-formed but unauthenticated mutation is still rejected.
    assert client.post("/api/v1/universes", json={"name": "Nope"}).status_code == 401


def test_revoked_session_cannot_be_reused(client: TestClient):
    register(client, "session@example.com")
    assert client.get("/api/v1/auth/me").status_code == 200
    session_cookie = client.cookies.get("ww_session")
    assert client.post("/api/v1/auth/logout").status_code == 204
    # Replay the exact token that was revoked.
    client.cookies.clear()
    client.cookies.set("ww_session", session_cookie)
    assert client.get("/api/v1/auth/me").status_code == 401


# -----------------------------------------------------------------------------
# Tenant isolation and cross-universe ID substitution
# -----------------------------------------------------------------------------

def test_cross_universe_id_substitution_is_blocked(client: TestClient):
    register(client, "owner_a@example.com")
    universe_a = create_universe(client, "Realm A")
    entity_a = create_entity(client, universe_a, "Entity A")

    register(client, "owner_b@example.com")
    universe_b = create_universe(client, "Realm B")

    # Universe A's id and entity id must not resolve from universe B's scope.
    assert client.get(f"/api/v1/universes/{universe_a}").status_code == 404
    assert (
        client.get(f"/api/v1/universes/{universe_b}/entities/{entity_a['id']}").status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/universes/{universe_b}/entities/{entity_a['id']}",
            json={"title": "Hijacked", "expected_version": 1},
        ).status_code
        == 404
    )


def test_search_does_not_leak_across_universes(client: TestClient):
    register(client, "search_owner@example.com")
    universe_id = create_universe(client, "Search Realm")
    create_entity(client, universe_id, "Aurora Prime")

    register(client, "outsider@example.com")
    other = create_universe(client, "Other Realm")
    assert client.get(f"/api/v1/universes/{universe_id}/search", params={"q": "aurora"}).status_code == 404
    assert (
        client.get(f"/api/v1/universes/{other}/search", params={"q": "aurora"}).json()["total"]
        == 0
    )


def test_graph_does_not_leak_private_nodes(client: TestClient):
    register(client, "graph_owner@example.com")
    universe_id = create_universe(client, "Graph Realm")
    visible = create_entity(client, universe_id, "Public Node")
    hidden = create_entity(client, universe_id, "Private Node", visibility="private")
    client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={
            "source_entity_id": visible["id"],
            "relation_type_key": "allied_with",
            "target_entity_id": hidden["id"],
        },
    )
    invite_and_accept(client, universe_id, "graph_owner@example.com", "graph_viewer@example.com", "viewer")
    login(client, "graph_viewer@example.com")
    graph = client.get(f"/api/v1/universes/{universe_id}/graph").json()
    node_ids = {node["id"] for node in graph["nodes"]}
    assert visible["id"] in node_ids
    assert hidden["id"] not in node_ids
    for edge in graph["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids


# -----------------------------------------------------------------------------
# Role escalation and viewer mutation
# -----------------------------------------------------------------------------

def test_role_escalation_is_blocked(client: TestClient):
    register(client, "owner@example.com")
    universe_id = create_universe(client, "Escalation Realm")
    editor = invite_and_accept(client, universe_id, "owner@example.com", "editor@example.com", "editor")

    login(client, "editor@example.com")
    # An editor cannot grant a role above its own authority.
    escalated = client.patch(
        f"/api/v1/universes/{universe_id}/members/{editor['id']}",
        json={"role": "admin"},
    )
    assert escalated.status_code == 403, escalated.text
    # An editor cannot invite at all.
    assert (
        client.post(
            f"/api/v1/universes/{universe_id}/invitations",
            json={"email": "newbie@example.com", "role": "viewer"},
        ).status_code
        == 403
    )


def test_viewer_cannot_mutate_any_resource_family(client: TestClient):
    register(client, "owner@example.com")
    universe_id = create_universe(client, "Readonly Realm")
    entity = create_entity(client, universe_id, "Fixed Star")
    document = client.post(
        f"/api/v1/universes/{universe_id}/documents", json={"title": "Fixed Text"}
    ).json()
    invite_and_accept(client, universe_id, "owner@example.com", "viewer@example.com", "viewer")

    login(client, "viewer@example.com")
    attempts = [
        client.post(
            f"/api/v1/universes/{universe_id}/entities",
            json={"entity_type_key": "character", "title": "Ghost"},
        ),
        client.patch(
            f"/api/v1/universes/{universe_id}/entities/{entity['id']}",
            json={"title": "Changed", "expected_version": entity["version"]},
        ),
        client.delete(f"/api/v1/universes/{universe_id}/entities/{entity['id']}"),
        client.post(
            f"/api/v1/universes/{universe_id}/documents",
            json={"title": "Ghost Document"},
        ),
        client.patch(
            f"/api/v1/universes/{universe_id}/documents/{document['id']}",
            json={"title": "Changed", "expected_version": document["version"]},
        ),
        client.post(
            f"/api/v1/universes/{universe_id}/maps",
            json={"title": "Ghost Map"},
        ),
        client.post(
            f"/api/v1/universes/{universe_id}/calendars",
            json={"name": "Ghost Calendar", "config_json": {"months": [{"name": "A", "days": 10}]}},
        ),
        client.post(f"/api/v1/universes/{universe_id}/exports"),
    ]
    for response in attempts:
        assert response.status_code == 403, response.text


# -----------------------------------------------------------------------------
# Collaboration room authorization
# -----------------------------------------------------------------------------

def test_unauthorized_room_join_is_rejected(client: TestClient):
    register(client, "owner@example.com")
    universe_id = create_universe(client, "Room Realm")
    guarded = client.post(
        f"/api/v1/universes/{universe_id}/documents", json={"title": "Guarded"}
    ).json()
    other = client.post(
        f"/api/v1/universes/{universe_id}/documents", json={"title": "Other"}
    ).json()

    # An invalid ticket is rejected outright.
    with pytest.raises(WebSocketDisconnect) as invalid:
        with client.websocket_connect(
            f"/api/v1/collaboration/documents/{guarded['id']}?ticket=not-a-ticket"
        ):
            pass
    assert invalid.value.code == 4401

    # A ticket scoped to a different document cannot open this room.
    mismatched = client.get(
        f"/api/v1/universes/{universe_id}/documents/{other['id']}/collaboration-ticket"
    ).json()["ticket"]
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(
            f"/api/v1/collaboration/documents/{guarded['id']}?ticket={mismatched}"
        ):
            pass
    assert rejected.value.code == 4403

    # A member of another universe cannot obtain a ticket for this document.
    register(client, "outsider@example.com")
    create_universe(client, "Other Realm")
    assert (
        client.get(
            f"/api/v1/universes/{universe_id}/documents/{guarded['id']}/collaboration-ticket"
        ).status_code
        == 404
    )


# -----------------------------------------------------------------------------
# Upload safety
# -----------------------------------------------------------------------------

def test_upload_path_traversal_is_neutralized(client: TestClient):
    register(client, "uploader@example.com")
    universe_id = create_universe(client, "Upload Realm")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (2).to_bytes(4, "big") + (3).to_bytes(4, "big")
    response = client.post(
        f"/api/v1/universes/{universe_id}/assets",
        files={"file": ("../../etc/evil.png", png, "image/png")},
    )
    assert response.status_code == 201, response.text
    assert "/" not in response.json()["original_filename"]
    assert ".." not in response.json()["original_filename"]


def test_spoofed_mime_type_is_rejected_by_content(client: TestClient):
    register(client, "spoofer@example.com")
    universe_id = create_universe(client, "Spoof Realm")
    # Claims PNG but the bytes are not a PNG signature.
    response = client.post(
        f"/api/v1/universes/{universe_id}/assets",
        files={"file": ("payload.png", b"<html>not an image</html>", "image/png")},
    )
    assert response.status_code == 415, response.text


def test_oversized_upload_is_rejected(client: TestClient):
    register(client, "big@example.com")
    universe_id = create_universe(client, "Big Realm")
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)
    response = client.post(
        f"/api/v1/universes/{universe_id}/assets",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert response.status_code == 413, response.text


# -----------------------------------------------------------------------------
# Stored XSS through rich text and Markdown
# -----------------------------------------------------------------------------

def test_rich_text_rejects_javascript_links(client: TestClient):
    register(client, "xss@example.com")
    universe_id = create_universe(client, "XSS Realm")
    payload = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "click",
                        "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}],
                    }
                ],
            }
        ],
    }
    response = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={"title": "Malicious", "content_json": payload},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


def test_rich_text_rejects_script_nodes(client: TestClient):
    register(client, "script@example.com")
    universe_id = create_universe(client, "Script Realm")
    payload = {
        "type": "doc",
        "content": [{"type": "script", "content": [{"type": "text", "text": "alert(1)"}]}],
    }
    response = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={"title": "Scripted", "content_json": payload},
    )
    assert response.status_code == 422, response.text


# -----------------------------------------------------------------------------
# CSRF
# -----------------------------------------------------------------------------

def test_csrf_is_required_for_authenticated_mutations(client: TestClient):
    register(client, "csrf@example.com")
    rejected = client.post(
        "/api/v1/universes",
        json={"name": "CSRF Realm"},
        headers={"x-csrf-token": "forged"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "csrf_rejected"
    accepted = client.post("/api/v1/universes", json={"name": "CSRF Realm"})
    assert accepted.status_code == 201


# -----------------------------------------------------------------------------
# Invitation token reuse and expiry
# -----------------------------------------------------------------------------

def test_invitation_token_is_bound_and_not_reusable(client: TestClient):
    register(client, "owner@example.com")
    universe_id = create_universe(client, "Invite Realm")
    invitation = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": "invitee@example.com", "role": "viewer"},
    ).json()
    token = invitation["invitation_token"]

    register(client, "wrong@example.com")
    mismatch = client.post(f"/api/v1/invitations/{token}/accept")
    assert mismatch.status_code == 403

    register(client, "invitee@example.com")
    assert client.post(f"/api/v1/invitations/{token}/accept").status_code == 200
    # A consumed token cannot be replayed.
    login(client, "invitee@example.com")
    replay = client.post(f"/api/v1/invitations/{token}/accept")
    assert replay.status_code in {404, 409}, replay.text


# -----------------------------------------------------------------------------
# Import/export safety (release surface)
# -----------------------------------------------------------------------------

def _crafted_bundle(member: str, content: bytes) -> bytes:
    universe = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Crafted",
        "slug": "crafted",
        "schema_version": 1,
    }
    manifest = {
        "format": "worldweave-export",
        "schema_version": 1,
        "exporter_version": "1.0.0",
        "universe_id": universe["id"],
        "universe_name": universe["name"],
        "universe_slug": universe["slug"],
        "exported_at": "2026-01-01T00:00:00+00:00",
        "counts": {},
        "warnings": [],
    }
    files = {
        "manifest.json": json.dumps(manifest).encode(),
        "universe.json": json.dumps(universe).encode(),
        "entities/index.json": json.dumps({"items": []}).encode(),
    }
    files[member] = content
    files["checksums.sha256"] = render_checksums(files).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_import_validation_rejects_unsafe_archive_paths(client: TestClient):
    register(client, "archive@example.com")
    universe_id = create_universe(client, "Archive Realm")
    payload = _crafted_bundle("../escape.md", b"# nope")
    response = client.post(
        f"/api/v1/universes/{universe_id}/imports/validate",
        files={"file": ("bundle.zip", payload, "application/zip")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "archive_unsafe_path"


def test_import_validation_rejects_tampered_checksums(client: TestClient):
    register(client, "tamper@example.com")
    universe_id = create_universe(client, "Tamper Realm")
    payload = bytearray(_crafted_bundle("entities/extra.json", b'{"items": []}'))
    with zipfile.ZipFile(io.BytesIO(bytes(payload))) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members["checksums.sha256"] = b"0" * 64 + b"  manifest.json\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    response = client.post(
        f"/api/v1/universes/{universe_id}/imports/validate",
        files={"file": ("bundle.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "checksum_mismatch"


def test_import_requires_elevated_role(client: TestClient):
    register(client, "owner@example.com")
    universe_id = create_universe(client, "Import Guard Realm")
    invite_and_accept(client, universe_id, "owner@example.com", "viewer@example.com", "viewer")
    login(client, "viewer@example.com")
    payload = _crafted_bundle("entities/extra.json", b'{"items": []}')
    response = client.post(
        f"/api/v1/universes/{universe_id}/imports/validate",
        files={"file": ("bundle.zip", payload, "application/zip")},
    )
    assert response.status_code == 403, response.text
