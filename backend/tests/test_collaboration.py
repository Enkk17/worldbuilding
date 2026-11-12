from __future__ import annotations

import base64
import json
import time
import uuid
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
from starlette.websockets import WebSocketDisconnect

from backend.core.config import Settings
from backend.core.models import (
    Base,
    DocumentCollabSnapshot,
    DocumentCollabUpdate,
)
from backend.main import create_app
from backend.modules.collaboration.tickets import (
    TicketError,
    decode_ticket,
    issue_ticket,
)
from backend.modules.collaboration.ydoc import (
    get_fragment,
    tiptap_to_ydoc,
    ydoc_to_tiptap,
)
from backend.modules.identity.service import _rate_limiter

from backend.tests.conftest import CsrfTestClient

AUTH_HEADERS = {"Origin": "http://testserver"}
PASSWORD = "password123456"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "yjs_tiptap_fixture.json"


# -----------------------------------------------------------------------------
# Fixtures and helpers
# -----------------------------------------------------------------------------

@pytest.fixture
def collab_client(tmp_path: Path):
    """File-backed SQLite so HTTP/WebSocket threads can share the database.

    The collaboration manager writes from worker threads while tests inspect
    durable state. An in-memory StaticPool database serialises every session
    onto one connection, which makes concurrent transaction boundaries
    unreliable. A temporary file database gives each session its own
    connection.
    """

    database_path = tmp_path / "worldweave-collab.sqlite3"
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
    )
    _rate_limiter.clear()
    application = create_app(settings=settings, engine=engine)
    with CsrfTestClient(application) as client:
        yield client
    engine.dispose()


def register_user(
    client: TestClient, email: str, display_name: str = "Collaborator"
) -> dict[str, Any]:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": display_name, "password": PASSWORD},
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


def add_member(
    client: TestClient,
    universe_id: str,
    owner_email: str,
    email: str,
    role: str,
) -> dict[str, Any]:
    login(client, owner_email)
    invitation = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": email, "role": role},
    )
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()["invitation_token"]
    member = register_user(client, email, email.split("@")[0].title())
    accepted = client.post(f"/api/v1/invitations/{token}/accept")
    assert accepted.status_code == 200, accepted.text
    login(client, owner_email)
    return member


def document_content(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def create_document(
    client: TestClient,
    universe_id: str,
    title: str,
    body: str = "Initial chronicle body",
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={"title": title, "content_json": document_content(body)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def get_document(
    client: TestClient, universe_id: str, document_id: str
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document_id}"
    )
    assert response.status_code == 200, response.text
    return response.json()


def ticket_for(
    client: TestClient, universe_id: str, document_id: str
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document_id}/collaboration-ticket"
    )
    assert response.status_code == 200, response.text
    return response.json()


def receive_control(
    websocket, expected: str | None = None, *, timeout_messages: int = 20
) -> dict[str, Any]:
    for _ in range(timeout_messages):
        payload = websocket.receive_bytes()
        if payload and payload[0] == 3:
            message = json.loads(payload[1:])
            if expected is None or message.get("type") == expected:
                return message
    raise AssertionError(f"control message {expected!r} was not received")


def receive_sync(websocket, subtype: int) -> bytes:
    for _ in range(20):
        payload = websocket.receive_bytes()
        if payload and payload[0] == 0 and payload[1] == subtype:
            return payload
    raise AssertionError(f"sync message subtype {subtype} was not received")


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


def collaboration_counts(
    client: TestClient, document_id: str
) -> tuple[int, int]:
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


def append_paragraph(doc: Doc, text: str) -> bytes:
    fragment = get_fragment(doc)
    paragraph = XmlElement("paragraph")
    fragment.children.append(paragraph)
    value = XmlText()
    paragraph.children.append(value)
    value.insert(0, text)
    return doc.get_update()


def plain_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(plain_text(item) for item in value)
    if isinstance(value, dict):
        return plain_text(value.get("text", "")) + plain_text(
            value.get("content", [])
        )
    return ""


# -----------------------------------------------------------------------------
# Yjs <-> TipTap conversion
# -----------------------------------------------------------------------------

def test_tiptap_yjs_conversion_matches_y_prosemirror_fixture():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    document = Doc()
    document.apply_update(base64.b64decode(fixture["update_base64"]))

    assert ydoc_to_tiptap(document) == fixture["tiptap"]
    assert fixture["round_trip"] == fixture["tiptap"]

    rebuilt = tiptap_to_ydoc(fixture["tiptap"])
    assert ydoc_to_tiptap(rebuilt) == fixture["tiptap"]


# -----------------------------------------------------------------------------
# Collaboration tickets
# -----------------------------------------------------------------------------

def test_ticket_endpoint_issues_scoped_credentials(collab_client: TestClient):
    client = collab_client
    owner = register_user(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Ticket Realm")
    document = create_document(client, universe_id, "Opening Chapter")

    payload = ticket_for(client, universe_id, document["id"])
    assert payload["can_write"] is True
    assert payload["role"] == "owner"
    assert payload["protocol"] == "yjs-websocket-v1"
    assert payload["collab_generation"] == 0
    assert payload["websocket_path"].endswith(
        f"/collaboration/documents/{document['id']}"
    )

    claims = decode_ticket(
        payload["ticket"], secret="test-collaboration-secret"
    )
    assert str(claims.user_id) == owner["id"]
    assert str(claims.universe_id) == universe_id
    assert str(claims.document_id) == document["id"]
    assert claims.can_write is True
    assert claims.collab_generation == 0
    assert claims.expires_at > claims.issued_at

    # A viewer receives a read-only ticket with the same document scope.
    add_member(client, universe_id, "owner@example.com", "viewer@example.com", "viewer")
    login(client, "viewer@example.com")
    viewer_ticket = ticket_for(client, universe_id, document["id"])
    assert viewer_ticket["can_write"] is False
    assert viewer_ticket["role"] == "viewer"

    # Outsiders cannot even learn whether the document exists.
    register_user(client, "outsider@example.com", "Outsider")
    response = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}/collaboration-ticket"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "universe_not_found"

    # Viewers cannot obtain write tickets after the universe is archived.
    login(client, "owner@example.com")
    archived = client.post(f"/api/v1/universes/{universe_id}/archive")
    assert archived.status_code == 200, archived.text
    archived_ticket = ticket_for(client, universe_id, document["id"])
    assert archived_ticket["can_write"] is False


def test_ticket_signature_expiry_and_tampering():
    user_id = uuid.uuid4()
    ticket = issue_ticket(
        secret="secret",
        ttl_seconds=30,
        user_id=user_id,
        session_id=uuid.uuid4(),
        universe_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        display_name="Signer",
        can_write=True,
        collab_generation=7,
    )
    decoded = decode_ticket(ticket.token, secret="secret")
    assert decoded.user_id == user_id
    assert decoded.collab_generation == 7

    tampered = ticket.token[:-1] + ("A" if ticket.token[-1] != "A" else "B")
    with pytest.raises(TicketError) as tampered_error:
        decode_ticket(tampered, secret="secret")
    assert tampered_error.value.code == "invalid_ticket"

    with pytest.raises(TicketError) as wrong_secret:
        decode_ticket(ticket.token, secret="other-secret")
    assert wrong_secret.value.code == "invalid_ticket"

    with pytest.raises(TicketError) as expired:
        decode_ticket(ticket.token, secret="secret", now=ticket.expires_at + 1)
    assert expired.value.code == "ticket_expired"


# -----------------------------------------------------------------------------
# WebSocket collaboration
# -----------------------------------------------------------------------------

def test_websocket_update_is_durable_acknowledged_and_materialized(
    collab_client: TestClient,
):
    client = collab_client
    register_user(client, "writer@example.com", "Writer")
    universe_id = create_universe(client, "Collaborative Realm")
    document = create_document(client, universe_id, "Shared Chapter")
    ticket = ticket_for(client, universe_id, document["id"])

    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )
    with client.websocket_connect(websocket_path) as websocket:
        initial = websocket.receive_bytes()
        assert initial[0] == 0 and initial[1] == 0
        state_vector = initial[2:]
        permission = receive_control(websocket, "permission")
        assert permission["canWrite"] is True

        # Mirror the real client: seed from the server's durable baseline.
        client_doc = Doc()
        client_doc.apply_update(latest_snapshot(client, document["id"]))
        update = append_paragraph(client_doc, "Collaborative paragraph")
        websocket.send_bytes(create_update_message(update))

        ack = receive_control(websocket, "durable_ack")
        assert ack["sequence"] == 1
        assert ack["stateVector"]

    wait_until(
        lambda: "Collaborative paragraph"
        in plain_text(
            get_document(client, universe_id, document["id"])["content_json"]
        )
    )
    snapshots, updates = collaboration_counts(client, document["id"])
    assert snapshots >= 1
    assert updates == 1

    # The REST version stays stable: the CRDT stream is the content write path.
    stored = get_document(client, universe_id, document["id"])
    assert stored["version"] == document["version"]


def test_websocket_read_only_viewer_update_is_rejected(collab_client: TestClient):
    client = collab_client
    register_user(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Readonly Realm")
    document = create_document(client, universe_id, "Protected Chapter")
    add_member(
        client,
        universe_id,
        "owner@example.com",
        "reader@example.com",
        "viewer",
    )
    login(client, "reader@example.com")
    ticket = ticket_for(client, universe_id, document["id"])
    assert ticket["can_write"] is False

    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )
    with client.websocket_connect(websocket_path) as websocket:
        initial = websocket.receive_bytes()
        assert initial[0] == 0
        permission = receive_control(websocket, "permission")
        assert permission["canWrite"] is False

        client_doc = Doc()
        client_doc.apply_update(latest_snapshot(client, document["id"]))
        websocket.send_bytes(
            create_update_message(append_paragraph(client_doc, "Should be rejected"))
        )
        error = receive_control(websocket, "error")
        assert error["code"] == "read_only"

    _, updates = collaboration_counts(client, document["id"])
    assert updates == 0
    assert "Should be rejected" not in plain_text(
        get_document(client, universe_id, document["id"])["content_json"]
    )


def test_awareness_presence_is_replayed_to_late_joiners(
    collab_client: TestClient,
):
    client = collab_client
    register_user(client, "presence@example.com", "Presence")
    universe_id = create_universe(client, "Presence Realm")
    document = create_document(client, universe_id, "Crowded Chapter")
    ticket = ticket_for(client, universe_id, document["id"])
    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )

    with client.websocket_connect(websocket_path) as first:
        first.receive_bytes()
        assert receive_control(first, "permission")["canWrite"] is True

        # Opaque presence frame: the server relays it without parsing, exactly
        # like a y-protocols awareness update.
        presence_frame = bytes([1, 42, 43, 44])
        first.send_bytes(presence_frame)

        with client.websocket_connect(websocket_path) as second:
            second.receive_bytes()
            assert receive_control(second, "permission")["canWrite"] is True
            assert second.receive_bytes() == presence_frame

            # A second frame replaces the first for that connection.
            replacement = bytes([1, 42, 45])
            first.send_bytes(replacement)
            assert second.receive_bytes() == replacement

    manager = client.app.state.collaboration_manager
    wait_until(lambda: not manager._rooms, timeout=10)


def test_awareness_presence_is_not_replayed_after_disconnect(
    collab_client: TestClient,
):
    client = collab_client
    register_user(client, "presence@example.com", "Presence")
    universe_id = create_universe(client, "Presence Realm")
    document = create_document(client, universe_id, "Crowded Chapter")
    ticket = ticket_for(client, universe_id, document["id"])
    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )

    manager = client.app.state.collaboration_manager
    with client.websocket_connect(websocket_path) as first:
        first.receive_bytes()
        receive_control(first, "permission")
        first.send_bytes(bytes([1, 42, 43]))

        # Give the receive loop time to process the frame before closing.
        room = manager._rooms[uuid.UUID(document["id"])]
        wait_until(lambda: len(room.awareness_frames) == 1)

    wait_until(lambda: not manager._rooms, timeout=10)

    with client.websocket_connect(websocket_path) as second:
        second.receive_bytes()
        receive_control(second, "permission")
        room = manager._rooms[uuid.UUID(document["id"])]
        assert room.awareness_frames == {}


def test_websocket_rejects_invalid_and_mismatched_tickets(
    collab_client: TestClient,
):
    client = collab_client
    register_user(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Ticket Guards")
    first = create_document(client, universe_id, "First Document")
    second = create_document(client, universe_id, "Second Document")

    with pytest.raises(WebSocketDisconnect) as invalid:
        with client.websocket_connect(
            f"/api/v1/collaboration/documents/{first['id']}?ticket=not-a-ticket"
        ):
            pass
    assert invalid.value.code == 4401

    ticket = ticket_for(client, universe_id, first["id"])
    with pytest.raises(WebSocketDisconnect) as mismatch:
        with client.websocket_connect(
            f"/api/v1/collaboration/documents/{second['id']}"
            f"?ticket={ticket['ticket']}"
        ):
            pass
    assert mismatch.value.code == 4403


def test_tenant_isolation_blocks_ticket_for_foreign_document(
    collab_client: TestClient,
):
    client = collab_client
    register_user(client, "alice@example.com", "Alice")
    alice_universe = create_universe(client, "Alice Realm")
    alice_document = create_document(client, alice_universe, "Alice Chapter")

    register_user(client, "bob@example.com", "Bob")
    bob_universe = create_universe(client, "Bob Realm")
    bob_document = create_document(client, bob_universe, "Bob Chapter")

    # Bob holds a valid session but cannot obtain Alice's ticket.
    response = client.get(
        f"/api/v1/universes/{alice_universe}/documents/"
        f"{alice_document['id']}/collaboration-ticket"
    )
    assert response.status_code == 404

    # A ticket scoped to Bob's document cannot open Alice's document.
    bob_ticket = ticket_for(client, bob_universe, bob_document["id"])
    with pytest.raises(WebSocketDisconnect) as mismatch:
        with client.websocket_connect(
            f"/api/v1/collaboration/documents/{alice_document['id']}"
            f"?ticket={bob_ticket['ticket']}"
        ):
            pass
    assert mismatch.value.code == 4403


def test_compaction_snapshots_and_prunes_verified_update_log(
    collab_client: TestClient,
):
    client = collab_client
    register_user(client, "compactor@example.com", "Compactor")
    universe_id = create_universe(client, "Compaction Realm")
    document = create_document(client, universe_id, "Checkpointed Chapter")
    ticket = ticket_for(client, universe_id, document["id"])

    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )
    with client.websocket_connect(websocket_path) as websocket:
        websocket.receive_bytes()
        receive_control(websocket, "permission")
        client_doc = Doc()
        client_doc.apply_update(latest_snapshot(client, document["id"]))

        for index in range(4):
            websocket.send_bytes(
                create_update_message(
                    append_paragraph(client_doc, f"Checkpoint {index}")
                )
            )
            ack = receive_control(websocket, "durable_ack")
            assert ack["sequence"] == index + 1

    # The fourth update crosses the configured snapshot threshold.
    wait_until(
        lambda: collaboration_counts(client, document["id"])[1] == 0,
        timeout=10,
    )
    snapshots, updates = collaboration_counts(client, document["id"])
    assert snapshots >= 2
    assert updates == 0

    with client.app.state.session_factory() as session:
        snapshot = session.scalar(
            select(DocumentCollabSnapshot)
            .where(
                DocumentCollabSnapshot.document_id == uuid.UUID(document["id"]),
                DocumentCollabSnapshot.reason.in_(["compaction", "idle", "shutdown"]),
            )
            .order_by(
                DocumentCollabSnapshot.created_at.desc(),
                DocumentCollabSnapshot.id.desc(),
            )
            .limit(1)
        )
        assert snapshot is not None
        assert snapshot.last_update_sequence >= 4
        assert snapshot.update_count >= 4
        assert snapshot.state_vector


def test_room_recovers_from_database_after_idle_close(collab_client: TestClient):
    client = collab_client
    register_user(client, "recover@example.com", "Recoverer")
    universe_id = create_universe(client, "Recovery Realm")
    document = create_document(client, universe_id, "Recovered Chapter")
    ticket = ticket_for(client, universe_id, document["id"])
    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )

    with client.websocket_connect(websocket_path) as websocket:
        websocket.receive_bytes()
        receive_control(websocket, "permission")
        client_doc = Doc()
        client_doc.apply_update(latest_snapshot(client, document["id"]))
        websocket.send_bytes(
            create_update_message(append_paragraph(client_doc, "Survives reconnect"))
        )
        assert receive_control(websocket, "durable_ack")["sequence"] == 1

    manager = client.app.state.collaboration_manager
    wait_until(lambda: not manager._rooms, timeout=10)

    expected = get_document(client, universe_id, document["id"])["content_json"]
    with client.websocket_connect(websocket_path) as websocket:
        websocket.receive_bytes()
        permission = receive_control(websocket, "permission")
        assert permission["canWrite"] is True

        empty = Doc()
        websocket.send_bytes(create_sync_message(empty))
        snapshot_message = receive_sync(websocket, 1)
        empty.apply_update(read_message(snapshot_message[2:]))
        assert ydoc_to_tiptap(empty) == expected


def test_live_room_detects_membership_revocation(collab_client: TestClient):
    client = collab_client
    register_user(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Revocation Realm")
    document = create_document(client, universe_id, "Revoked Chapter")
    member = add_member(
        client,
        universe_id,
        "owner@example.com",
        "editor@example.com",
        "editor",
    )
    login(client, "editor@example.com")
    ticket = ticket_for(client, universe_id, document["id"])

    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )
    with client.websocket_connect(websocket_path) as websocket:
        websocket.receive_bytes()
        assert receive_control(websocket, "permission")["canWrite"] is True

        login(client, "owner@example.com")
        removed = client.delete(
            f"/api/v1/universes/{universe_id}/members/{member['id']}"
        )
        assert removed.status_code == 204, removed.text

        # Revalidation happens on the next write after the 2s interval.
        time.sleep(2.2)
        with pytest.raises(WebSocketDisconnect) as revoked:
            websocket.send_bytes(create_update_message(b"\x00\x00"))
            websocket.receive_bytes()
        assert revoked.value.code in {4404, 4401}


# -----------------------------------------------------------------------------
# REST and revision integration guards
# -----------------------------------------------------------------------------

def test_rest_content_updates_are_blocked_once_collaboration_state_exists(
    collab_client: TestClient,
):
    client = collab_client
    register_user(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "REST Guard Realm")
    document = create_document(client, universe_id, "Guarded Chapter")
    ticket = ticket_for(client, universe_id, document["id"])

    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )
    with client.websocket_connect(websocket_path) as websocket:
        websocket.receive_bytes()
        receive_control(websocket, "permission")

    current = get_document(client, universe_id, document["id"])
    blocked = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}",
        json={
            "expected_version": current["version"],
            "content_json": document_content("REST overwrite"),
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "collaboration_content_conflict"

    metadata = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}",
        json={
            "expected_version": current["version"],
            "title": "Renamed Chapter",
        },
    )
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["title"] == "Renamed Chapter"


def test_revision_restore_resets_collaboration_generation_and_state(
    collab_client: TestClient,
):
    client = collab_client
    register_user(client, "owner@example.com", "Owner")
    universe_id = create_universe(client, "Restore Realm")
    document = create_document(client, universe_id, "Versioned Chapter", body="First")

    # Produce a second revision through the REST path before collaboration
    # state exists, so the later restore really changes the document content.
    changed = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}",
        json={
            "expected_version": document["version"],
            "content_json": document_content("Second"),
        },
    )
    assert changed.status_code == 200, changed.text

    revisions = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}/revisions",
        params={"include_content": "true"},
    )
    assert revisions.status_code == 200, revisions.text
    revision_id = revisions.json()["items"][-1]["id"]

    ticket = ticket_for(client, universe_id, document["id"])
    websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={ticket['ticket']}"
    )
    with client.websocket_connect(websocket_path) as websocket:
        websocket.receive_bytes()
        receive_control(websocket, "permission")
    assert collaboration_counts(client, document["id"])[0] == 1

    current = get_document(client, universe_id, document["id"])
    restored = client.post(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}"
        f"/restore/{revision_id}",
        json={"expected_version": current["version"]},
    )
    assert restored.status_code == 200, restored.text

    snapshots, updates = collaboration_counts(client, document["id"])
    assert snapshots == 0
    assert updates == 0
    refreshed_ticket = ticket_for(client, universe_id, document["id"])
    assert refreshed_ticket["collab_generation"] == 1

    # The pre-restore ticket is bound to generation 0 and must be rejected:
    # reconnecting it would replay the discarded CRDT operations.
    with pytest.raises(WebSocketDisconnect) as stale:
        with client.websocket_connect(websocket_path) as websocket:
            websocket.receive_bytes()
    assert stale.value.code == 4001

    # A ticket minted for the new generation is seeded from the restored JSON,
    # never from the discarded operations of the previous generation.
    expected = get_document(client, universe_id, document["id"])["content_json"]
    current_websocket_path = (
        f"/api/v1/collaboration/documents/{document['id']}"
        f"?ticket={refreshed_ticket['ticket']}"
    )
    with client.websocket_connect(current_websocket_path) as websocket:
        websocket.receive_bytes()
        assert receive_control(websocket, "permission")["canWrite"] is True
        empty = Doc()
        websocket.send_bytes(create_sync_message(empty))
        reply = receive_sync(websocket, 1)
        empty.apply_update(read_message(reply[2:]))
        assert ydoc_to_tiptap(empty) == expected
