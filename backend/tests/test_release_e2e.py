"""Release E2E regression: the ten scenarios in TEST_STRATEGY section 6.

These exercise the full HTTP surface end to end (no mocks) so a release gate
has evidence that the modules interoperate, not only that each passes alone.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from pycrdt import (
    Doc,
    XmlElement,
    XmlText,
    create_sync_message,
    create_update_message,
    read_message,
)
from sqlalchemy import create_engine, func, select

from backend.core.config import Settings
from backend.core.models import (
    Base,
    DocumentCollabSnapshot,
    DocumentCollabUpdate,
)
from backend.main import create_app
from backend.modules.collaboration.ydoc import (
    get_fragment,
    ydoc_to_tiptap,
)
from backend.modules.identity.service import _rate_limiter
from backend.tests.conftest import CsrfTestClient

AUTH_HEADERS = {"Origin": "http://testserver"}
PASSWORD = "password123456"


@pytest.fixture
def e2e_client(tmp_path: Path):
    """File-backed SQLite so HTTP and WebSocket threads share one database."""

    database_path = tmp_path / "worldweave-release.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url=f"sqlite+pysqlite:///{database_path.as_posix()}",
        registration_mode="open",
        cookie_secure=False,
        session_ttl_days=30,
        auth_rate_limit=1000,
        auth_rate_window_seconds=60,
        collaboration_ticket_secret="test-collaboration-secret",
        collaboration_ticket_ttl_seconds=120,
        collaboration_materialize_delay_ms=25,
        collaboration_idle_close_seconds=1,
        collaboration_snapshot_update_threshold=4,
        collaboration_snapshot_byte_threshold=1_000_000,
        collaboration_revision_interval_seconds=3600,
        media_root=str(tmp_path / "media"),
        max_asset_bytes=1_048_576,
        max_archive_bytes=5_242_880,
    )
    _rate_limiter.clear()
    application = create_app(settings=settings, engine=engine)
    with CsrfTestClient(application) as client:
        yield client
    engine.dispose()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def register(client: TestClient, email: str, display_name: str | None = None) -> dict[str, Any]:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": display_name or email.split("@")[0],
            "password": PASSWORD,
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str) -> dict[str, Any]:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_universe(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/universes", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def invite_and_accept(
    client: TestClient, universe_id: str, owner_email: str, email: str, role: str
) -> dict[str, Any]:
    login(client, owner_email)
    invitation = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": email, "role": role},
    )
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()["invitation_token"]
    member = register(client, email, email.split("@")[0].title())
    accepted = client.post(f"/api/v1/invitations/{token}/accept")
    assert accepted.status_code == 200, accepted.text
    login(client, owner_email)
    return member


def create_entity(
    client: TestClient, universe_id: str, type_key: str, title: str, **extra: Any
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": type_key, "title": title, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def doc_content(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        ],
    }


def create_document(
    client: TestClient, universe_id: str, title: str, body: str = "Initial body"
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={"title": title, "content_json": doc_content(body)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_calendar(client: TestClient, universe_id: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/universes/{universe_id}/calendars",
        json={
            "name": "Twelve Moons",
            "config_json": {
                "months": [
                    {"name": "Seed", "days": 30},
                    {"name": "Bloom", "days": 30},
                    {"name": "Harvest", "days": 30},
                ],
                "weekdays": ["First", "Second", "Third", "Fourth", "Fifth"],
                "epoch_offset": 4,
                "leap_rules": [
                    {"every_years": 4, "year_offset": 0, "month": 2, "extra_days": 2}
                ],
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def plain_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(plain_text(item) for item in value)
    if isinstance(value, dict):
        return plain_text(value.get("text", "")) + plain_text(value.get("content", []))
    return ""


def wait_until(
    predicate: Callable[[], Any], *, timeout: float = 8.0, interval: float = 0.05
) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s (last={last!r})")


def receive_control(websocket, expected: str | None = None) -> dict[str, Any]:
    for _ in range(30):
        payload = websocket.receive_bytes()
        if payload and payload[0] == 3:
            message = json.loads(payload[1:])
            if expected is None or message.get("type") == expected:
                return message
    raise AssertionError(f"control message {expected!r} was not received")


def receive_sync(websocket, subtype: int) -> bytes:
    for _ in range(30):
        payload = websocket.receive_bytes()
        if payload and payload[0] == 0 and payload[1] == subtype:
            return payload
    raise AssertionError(f"sync message subtype {subtype} was not received")


def append_paragraph(doc: Doc, text: str) -> bytes:
    fragment = get_fragment(doc)
    paragraph = XmlElement("paragraph")
    fragment.children.append(paragraph)
    value = XmlText()
    paragraph.children.append(value)
    value.insert(0, text)
    return doc.get_update()


def latest_snapshot(client: TestClient, document_id: str) -> bytes:
    with client.app.state.session_factory() as session:
        snapshot = session.scalar(
            select(DocumentCollabSnapshot)
            .where(DocumentCollabSnapshot.document_id == uuid.UUID(document_id))
            .order_by(
                DocumentCollabSnapshot.created_at.desc(),
                DocumentCollabSnapshot.id.desc(),
            )
            .limit(1)
        )
        assert snapshot is not None
        return snapshot.ydoc_state


def collab_counts(client: TestClient, document_id: str) -> tuple[int, int]:
    with client.app.state.session_factory() as session:
        snapshots = session.scalar(
            select(func.count(DocumentCollabSnapshot.id)).where(
                DocumentCollabSnapshot.document_id == uuid.UUID(document_id)
            )
        )
        updates = session.scalar(
            select(func.count(DocumentCollabUpdate.id)).where(
                DocumentCollabUpdate.document_id == uuid.UUID(document_id)
            )
        )
    return int(snapshots or 0), int(updates or 0)


def ticket_for(client: TestClient, universe_id: str, document_id: str) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document_id}/collaboration-ticket"
    )
    assert response.status_code == 200, response.text
    return response.json()


# -----------------------------------------------------------------------------
# Scenario 1: Owner creates universe and invites Editor, Contributor, Viewer
# -----------------------------------------------------------------------------

def test_scenario_1_owner_invites_full_role_roster(e2e_client: TestClient):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Pantheon")

    for email, role in (
        ("editor@example.com", "editor"),
        ("contributor@example.com", "contributor"),
        ("viewer@example.com", "viewer"),
    ):
        invite_and_accept(client, universe_id, "owner@example.com", email, role)

    members = client.get(f"/api/v1/universes/{universe_id}/members").json()
    roles = {member["role"] for member in members}
    assert roles == {"owner", "editor", "contributor", "viewer"}
    assert len(members) == 4


# -----------------------------------------------------------------------------
# Scenario 2: Viewer cannot change an entity even by direct API request
# -----------------------------------------------------------------------------

def test_scenario_2_viewer_mutation_is_rejected_at_the_api(e2e_client: TestClient):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Locked Realm")
    entity = create_entity(client, universe_id, "character", "Sealed One")
    invite_and_accept(client, universe_id, "owner@example.com", "viewer@example.com", "viewer")

    login(client, "viewer@example.com")
    denied = client.patch(
        f"/api/v1/universes/{universe_id}/entities/{entity['id']}",
        json={"title": "Tampered", "expected_version": entity["version"]},
    )
    assert denied.status_code == 403, denied.text
    denied_create = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "character", "title": "Sneaky"},
    )
    assert denied_create.status_code == 403
    denied_delete = client.delete(
        f"/api/v1/universes/{universe_id}/entities/{entity['id']}"
    )
    assert denied_delete.status_code == 403

    login(client, "owner@example.com")
    unchanged = client.get(f"/api/v1/universes/{universe_id}/entities/{entity['id']}").json()
    assert unchanged["title"] == "Sealed One"
    assert unchanged["version"] == entity["version"]


# -----------------------------------------------------------------------------
# Scenario 3: Contributor submits a draft; Editor reviews (publishes) it
# -----------------------------------------------------------------------------

def test_scenario_3_contributor_draft_reviewed_by_editor(e2e_client: TestClient):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Review Realm")
    invite_and_accept(client, universe_id, "owner@example.com", "editor@example.com", "editor")
    invite_and_accept(
        client, universe_id, "owner@example.com", "contributor@example.com", "contributor"
    )

    login(client, "contributor@example.com")
    draft = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={"title": "Proposed Lore", "content_json": doc_content("A tentative legend.")},
    ).json()
    assert draft["status"] == "draft"
    assert draft["visibility"] == "draft"

    submitted = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{draft['id']}",
        json={"expected_version": draft["version"], "status": "review"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "review"

    # The contributor cannot publish their own proposal.
    forbidden = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{draft['id']}",
        json={"expected_version": submitted.json()["version"], "status": "published"},
    )
    assert forbidden.status_code == 403

    login(client, "editor@example.com")
    reviewed = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{draft['id']}",
        json={"expected_version": submitted.json()["version"], "status": "published"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "published"


# -----------------------------------------------------------------------------
# Scenario 4: Two editors co-edit a chapter; both see converged content
# -----------------------------------------------------------------------------

def test_scenario_4_two_editors_converge(e2e_client: TestClient):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Convergent Realm")
    document = create_document(client, universe_id, "Twin Chapter")
    ticket = ticket_for(client, universe_id, document["id"])
    path = f"/api/v1/collaboration/documents/{document['id']}?ticket={ticket['ticket']}"

    with client.websocket_connect(path) as first:
        first.receive_bytes()
        assert receive_control(first, "permission")["canWrite"] is True
        first_doc = Doc()
        first_doc.apply_update(latest_snapshot(client, document["id"]))
        first.send_bytes(create_sync_message(first_doc))
        receive_sync(first, 1)

        with client.websocket_connect(path) as second:
            second.receive_bytes()
            assert receive_control(second, "permission")["canWrite"] is True
            second_doc = Doc()
            second_doc.apply_update(latest_snapshot(client, document["id"]))

            first.send_bytes(create_update_message(append_paragraph(first_doc, "First voice")))
            assert receive_control(first, "durable_ack")["sequence"] == 1

            # Second client observes the first client's broadcast.
            observed = second.receive_bytes()
            assert observed[0] == 0
            second_doc.apply_update(read_message(observed[2:]))

            second.send_bytes(
                create_update_message(append_paragraph(second_doc, "Second voice"))
            )
            assert receive_control(second, "durable_ack")["sequence"] == 2

            # First client receives the second client's update and converges.
            echoed = first.receive_bytes()
            while not (echoed and echoed[0] == 0):
                echoed = first.receive_bytes()
            first_doc.apply_update(read_message(echoed[2:]))

    assert ydoc_to_tiptap(first_doc) == ydoc_to_tiptap(second_doc)
    converged = plain_text(ydoc_to_tiptap(first_doc))
    assert "First voice" in converged
    assert "Second voice" in converged


# -----------------------------------------------------------------------------
# Scenario 5: Server restart; acknowledged chapter content remains
# -----------------------------------------------------------------------------

def test_scenario_5_acknowledged_content_survives_restart(e2e_client: TestClient):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Durable Realm")
    document = create_document(client, universe_id, "Enduring Chapter")
    ticket = ticket_for(client, universe_id, document["id"])
    path = f"/api/v1/collaboration/documents/{document['id']}?ticket={ticket['ticket']}"

    with client.websocket_connect(path) as websocket:
        websocket.receive_bytes()
        receive_control(websocket, "permission")
        client_doc = Doc()
        client_doc.apply_update(latest_snapshot(client, document["id"]))
        websocket.send_bytes(
            create_update_message(append_paragraph(client_doc, "Persisted forever"))
        )
        assert receive_control(websocket, "durable_ack")["sequence"] == 1

    # Simulate a restart: drop the in-process room and reconnect fresh.
    manager = client.app.state.collaboration_manager
    wait_until(lambda: not manager._rooms, timeout=10)
    snapshots, _ = collab_counts(client, document["id"])
    # The idle teardown compacts the room, so durability is proven by the
    # verified snapshot rather than a retained update log.
    assert snapshots >= 1

    expected = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}"
    ).json()["content_json"]
    with client.websocket_connect(path) as websocket:
        websocket.receive_bytes()
        receive_control(websocket, "permission")
        empty = Doc()
        websocket.send_bytes(create_sync_message(empty))
        snapshot_message = receive_sync(websocket, 1)
        empty.apply_update(read_message(snapshot_message[2:]))
        assert ydoc_to_tiptap(empty) == expected
    assert "Persisted forever" in plain_text(expected)


# -----------------------------------------------------------------------------
# Scenario 6: Map marker links to a location entity and survives viewport changes
# -----------------------------------------------------------------------------

def test_scenario_6_marker_links_entity_and_position_is_viewport_invariant(
    e2e_client: TestClient,
):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Cartography Realm")
    location = create_entity(client, universe_id, "place", "Harbour Gate")
    map_response = client.post(
        f"/api/v1/universes/{universe_id}/maps",
        json={"title": "Coastline", "width": 1024, "height": 768},
    )
    assert map_response.status_code == 201, map_response.text
    map_id = map_response.json()["id"]
    marker = client.post(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/markers",
        json={
            "title": "Gate",
            "x_norm": 0.25,
            "y_norm": 0.75,
            "linked_entity_id": location["id"],
        },
    )
    assert marker.status_code == 201, marker.text
    assert marker.json()["linked_entity_id"] == location["id"]

    # Changing the map dimensions must not reinterpret normalized coordinates.
    resized = client.patch(
        f"/api/v1/universes/{universe_id}/maps/{map_id}",
        json={"width": 4096, "height": 2160, "expected_version": map_response.json()["version"]},
    )
    assert resized.status_code == 200, resized.text
    markers = client.get(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/markers"
    ).json()
    reread = next(item for item in markers["items"] if item["id"] == marker.json()["id"])
    assert reread["x_norm"] == 0.25
    assert reread["y_norm"] == 0.75
    assert reread["linked_entity_id"] == location["id"]


# -----------------------------------------------------------------------------
# Scenario 7: Non-Gregorian calendar sorts events correctly
# -----------------------------------------------------------------------------

def test_scenario_7_custom_calendar_sorts_events_correctly(e2e_client: TestClient):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Chronicle Realm")
    calendar = create_calendar(client, universe_id)

    # Months have 30 days; year 1 has 4 leap years starting at year 4.
    dates = [
        ("Late", {"year": 2, "month": 3, "day": 10}),
        ("Early", {"year": 1, "month": 1, "day": 1}),
        ("Middle", {"year": 1, "month": 2, "day": 15}),
    ]
    for title, start in dates:
        created = client.post(
            f"/api/v1/universes/{universe_id}/timeline-events",
            json={
                "calendar_id": calendar["id"],
                "title": title,
                "start_date_json": start,
            },
        )
        assert created.status_code == 201, created.text

    listed = client.get(
        f"/api/v1/universes/{universe_id}/timeline-events",
        params={"calendar_id": calendar["id"], "limit": 50, "offset": 0},
    )
    assert listed.status_code == 200, listed.text
    titles = [item["title"] for item in listed.json()["items"]]
    assert titles == ["Early", "Middle", "Late"]
    indices = [item["start_day_index"] for item in listed.json()["items"]]
    assert indices == sorted(indices)


# -----------------------------------------------------------------------------
# Scenario 8: Nexus displays only permitted nodes and relations
# -----------------------------------------------------------------------------

def test_scenario_8_nexus_hides_private_nodes_from_viewers(e2e_client: TestClient):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Veiled Realm")
    public = create_entity(client, universe_id, "character", "Public Hero")
    secret = create_entity(
        client, universe_id, "character", "Secret Villain", visibility="private"
    )
    relation = client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={
            "source_entity_id": public["id"],
            "relation_type_key": "allied_with",
            "target_entity_id": secret["id"],
        },
    )
    assert relation.status_code == 201, relation.text

    invite_and_accept(client, universe_id, "owner@example.com", "viewer@example.com", "viewer")
    login(client, "viewer@example.com")
    graph = client.get(f"/api/v1/universes/{universe_id}/graph").json()
    node_ids = {node["id"] for node in graph["nodes"]}
    assert public["id"] in node_ids
    assert secret["id"] not in node_ids
    # No edge may reference a hidden node.
    for edge in graph["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids


# -----------------------------------------------------------------------------
# Scenario 9: Export imported into a clean universe without broken links
# -----------------------------------------------------------------------------

def test_scenario_9_export_import_round_trip_into_clean_universe(e2e_client: TestClient):
    client = e2e_client
    register(client, "owner@example.com", "Owner")
    source_id = create_universe(client, "Origin")
    first = create_entity(client, source_id, "character", "Mira Vale")
    second = create_entity(client, source_id, "place", "Salt Harbour")
    relation = client.post(
        f"/api/v1/universes/{source_id}/relations",
        json={
            "source_entity_id": first["id"],
            "relation_type_key": "located_in",
            "target_entity_id": second["id"],
        },
    )
    assert relation.status_code == 201, relation.text
    create_document(client, source_id, "The Salt Road", "She walked the salt road.")

    export = client.post(f"/api/v1/universes/{source_id}/exports")
    assert export.status_code == 200, export.text
    assert export.headers["content-type"] == "application/zip"

    target_id = create_universe(client, "Clean Target")
    imported = client.post(
        f"/api/v1/universes/{target_id}/imports?conflict_policy=skip",
        files={"file": ("bundle.zip", export.content, "application/zip")},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["source_universe_id"] == source_id

    entities = client.get(f"/api/v1/universes/{target_id}/entities").json()
    assert entities["total"] == 2
    cloned_ids = {item["id"] for item in entities["items"]}
    assert first["id"] not in cloned_ids
    # Every relation in the clone points at two entities that exist in the clone.
    mira = next(item for item in entities["items"] if item["title"] == "Mira Vale")
    rels = client.get(
        f"/api/v1/universes/{target_id}/entities/{mira['id']}/relations"
    ).json()
    assert len(rels) == 1
    assert rels[0]["target_entity_id"] in cloned_ids
    assert client.get(f"/api/v1/universes/{target_id}/documents").json()["total"] == 1


# -----------------------------------------------------------------------------
# Scenario 10: Backup restore smoke test (database-level integrity)
# -----------------------------------------------------------------------------

def test_scenario_10_export_bundle_is_integrity_verifiable(e2e_client: TestClient):
    """Backup/restore smoke at the artifact level.

    The operational pg_dump/pg_restore drill runs in the release script against
    PostgreSQL; this asserts the portable export stays internally consistent so
    an integrity check has something meaningful to verify.
    """

    client = e2e_client
    register(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Backup Realm")
    create_entity(client, universe_id, "character", "Anchor")
    export = client.post(f"/api/v1/universes/{universe_id}/exports")
    assert export.status_code == 200

    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "universe.json", "checksums.sha256"} <= names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "worldweave-export"
        assert manifest["schema_version"] == 1

        declared: dict[str, str] = {}
        for line in archive.read("checksums.sha256").decode().splitlines():
            digest, name = line.split("  ", 1)
            declared[name] = digest
        assert declared, "checksums manifest must not be empty"
        for name, digest in declared.items():
            actual = hashlib.sha256(archive.read(name)).hexdigest()
            assert actual == digest, f"checksum mismatch for {name}"
