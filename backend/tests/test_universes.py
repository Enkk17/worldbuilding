from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"Origin": "http://testserver"}


def register_user(client: TestClient, email: str, display_name: str, password: str = "password123456"):
    client.cookies.clear()
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": display_name, "password": password},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def login_user(client: TestClient, email: str, password: str = "password123456"):
    client.cookies.clear()
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_universe_creation_and_listing(open_client: TestClient):
    client = open_client
    user = register_user(client, "alice@example.com", "Alice Creator")

    # Initially empty list
    resp = client.get("/api/v1/universes")
    assert resp.status_code == 200
    assert resp.json()["items"] == []

    # Create universe
    resp = client.post(
        "/api/v1/universes",
        json={"name": "Eldoria", "description": "High fantasy realm"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Eldoria"
    assert data["slug"] == "eldoria"
    assert data["role"] == "owner"
    assert data["status"] == "active"
    universe_id = data["id"]

    # Listing contains universe
    resp = client.get("/api/v1/universes")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == universe_id

    # Update universe
    patch_resp = client.patch(
        f"/api/v1/universes/{universe_id}",
        json={"description": "Updated high fantasy realm description"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "Updated high fantasy realm description"

    # Archive universe
    arch_resp = client.post(f"/api/v1/universes/{universe_id}/archive")
    assert arch_resp.status_code == 200
    assert arch_resp.json()["status"] == "archived"


def test_cross_universe_isolation(open_client: TestClient):
    client = open_client
    alice = register_user(client, "alice_iso@example.com", "Alice")
    u_resp = client.post("/api/v1/universes", json={"name": "Alice World"})
    alice_u_id = u_resp.json()["id"]

    # Bob logs in and tries to access Alice's universe
    bob = register_user(client, "bob_iso@example.com", "Bob")
    resp = client.get(f"/api/v1/universes/{alice_u_id}")
    # Must return 404 to avoid leaking existence
    assert resp.status_code == 404

    resp = client.patch(f"/api/v1/universes/{alice_u_id}", json={"name": "Hacked"})
    assert resp.status_code == 404


def test_invitation_lifecycle_and_role_matrix(open_client: TestClient):
    client = open_client
    alice = register_user(client, "alice_inv@example.com", "Alice Owner")
    u_resp = client.post("/api/v1/universes", json={"name": "Kingdom of Oakhaven"})
    universe_id = u_resp.json()["id"]

    # Alice invites Bob as editor
    inv_resp = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": "bob_inv@example.com", "role": "editor"},
    )
    assert inv_resp.status_code == 201
    token = inv_resp.json()["invitation_token"]
    assert token is not None

    # Bob registers and accepts invitation
    bob = register_user(client, "bob_inv@example.com", "Bob Writer")
    accept_resp = client.post(f"/api/v1/invitations/{token}/accept")
    assert accept_resp.status_code == 200
    assert accept_resp.json()["id"] == universe_id
    assert accept_resp.json()["role"] == "editor"

    # Bob can list members as editor
    members_resp = client.get(f"/api/v1/universes/{universe_id}/members")
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 2

    # Editor cannot invite members (requires admin or owner)
    editor_inv = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": "eve@example.com", "role": "viewer"},
    )
    assert editor_inv.status_code == 403

    # Accepting with invalid token returns 404
    inv_invalid = client.post("/api/v1/invitations/non-existent-token/accept")
    assert inv_invalid.status_code == 404


def test_member_role_updates_and_removal(open_client: TestClient):
    client = open_client
    alice = register_user(client, "alice_mgmt@example.com", "Alice")
    u_resp = client.post("/api/v1/universes", json={"name": "Silverland"})
    universe_id = u_resp.json()["id"]

    # Invite Bob as viewer
    inv_resp = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": "bob_mgmt@example.com", "role": "viewer"},
    )
    token = inv_resp.json()["invitation_token"]

    bob = register_user(client, "bob_mgmt@example.com", "Bob")
    client.post(f"/api/v1/invitations/{token}/accept")

    # Alice promotes Bob to admin
    login_user(client, "alice_mgmt@example.com")
    patch_resp = client.patch(
        f"/api/v1/universes/{universe_id}/members/{bob['id']}",
        json={"role": "admin"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["role"] == "admin"

    # Bob (admin) cannot promote another user to owner or remove owner
    login_user(client, "bob_mgmt@example.com")
    del_owner = client.delete(f"/api/v1/universes/{universe_id}/members/{alice['id']}")
    assert del_owner.status_code == 400
    assert del_owner.json()["error"]["code"] == "cannot_remove_owner"

    # Alice removes Bob
    login_user(client, "alice_mgmt@example.com")
    del_resp = client.delete(f"/api/v1/universes/{universe_id}/members/{bob['id']}")
    assert del_resp.status_code == 204

    # Verify audit logs
    audit_resp = client.get(f"/api/v1/universes/{universe_id}/audit-logs")
    assert audit_resp.status_code == 200
    actions = [a["action"] for a in audit_resp.json()]
    assert "member.update_role" in actions
    assert "member.remove" in actions

    # Bob can no longer access the universe
    login_user(client, "bob_mgmt@example.com")
    get_resp = client.get(f"/api/v1/universes/{universe_id}")
    assert get_resp.status_code == 404
