from __future__ import annotations

from fastapi.testclient import TestClient

AUTH_HEADERS = {"Origin": "http://testserver"}


def register_user(
    client: TestClient,
    email: str,
    display_name: str,
    password: str = "password123456",
):
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": display_name, "password": password},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def login_user(client: TestClient, email: str, password: str = "password123456"):
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_universe(client: TestClient, name: str = "Security Realm") -> str:
    response = client.post("/api/v1/universes", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def invite(client: TestClient, universe_id: str, email: str, role: str = "editor"):
    return client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": email, "role": role},
    )


def test_invitation_is_bound_to_the_invited_email(open_client: TestClient):
    client = open_client
    register_user(client, "owner_binding@example.com", "Owner")
    universe_id = create_universe(client, "Binding Realm")
    response = invite(client, universe_id, "intended@example.com")
    assert response.status_code == 201
    token = response.json()["invitation_token"]

    register_user(client, "intruder@example.com", "Intruder")
    stolen = client.post(f"/api/v1/invitations/{token}/accept")
    assert stolen.status_code == 403
    assert stolen.json()["error"]["code"] == "invitation_email_mismatch"

    register_user(client, "intended@example.com", "Intended")
    accepted = client.post(f"/api/v1/invitations/{token}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "editor"


def test_duplicate_and_already_member_invitations_are_rejected(open_client: TestClient):
    client = open_client
    register_user(client, "owner_dupe@example.com", "Owner")
    universe_id = create_universe(client, "Dupe Realm")

    first = invite(client, universe_id, "pending@example.com")
    assert first.status_code == 201
    duplicate = invite(client, universe_id, "pending@example.com")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "invitation_pending"

    token = first.json()["invitation_token"]
    register_user(client, "pending@example.com", "Pending")
    assert client.post(f"/api/v1/invitations/{token}/accept").status_code == 200

    login_user(client, "owner_dupe@example.com")
    already_member = invite(client, universe_id, "pending@example.com")
    assert already_member.status_code == 409
    assert already_member.json()["error"]["code"] == "already_member"


def test_invitation_revocation_invalidates_the_token(open_client: TestClient):
    client = open_client
    register_user(client, "owner_revoke@example.com", "Owner")
    universe_id = create_universe(client, "Revoke Realm")
    created = invite(client, universe_id, "revoked@example.com")
    assert created.status_code == 201

    listed = client.get(f"/api/v1/universes/{universe_id}/invitations")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    invitation_id = listed.json()[0]["id"]
    assert "invitation_token" not in listed.json()[0] or listed.json()[0]["invitation_token"] is None

    revoked = client.delete(
        f"/api/v1/universes/{universe_id}/invitations/{invitation_id}"
    )
    assert revoked.status_code == 204

    token = created.json()["invitation_token"]
    register_user(client, "revoked@example.com", "Revoked")
    assert client.post(f"/api/v1/invitations/{token}/accept").status_code == 404


def test_owner_cannot_demote_self_without_transfer(open_client: TestClient):
    client = open_client
    owner = register_user(client, "owner_self@example.com", "Owner")
    universe_id = create_universe(client, "Self Realm")

    response = client.patch(
        f"/api/v1/universes/{universe_id}/members/{owner['id']}",
        json={"role": "admin"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "cannot_change_owner_role"


def test_ownership_transfer_swaps_roles(open_client: TestClient):
    client = open_client
    owner = register_user(client, "owner_transfer@example.com", "Owner")
    universe_id = create_universe(client, "Transfer Realm")
    created = invite(client, universe_id, "successor@example.com", "admin")
    token = created.json()["invitation_token"]
    successor = register_user(client, "successor@example.com", "Successor")
    assert client.post(f"/api/v1/invitations/{token}/accept").status_code == 200

    login_user(client, "owner_transfer@example.com")
    transfer = client.post(
        f"/api/v1/universes/{universe_id}/transfer-ownership",
        json={"new_owner_user_id": successor["id"]},
    )
    assert transfer.status_code == 200
    assert transfer.json()["owner_user_id"] == successor["id"]
    assert transfer.json()["role"] == "admin"

    login_user(client, "successor@example.com")
    detail = client.get(f"/api/v1/universes/{universe_id}")
    assert detail.status_code == 200
    assert detail.json()["role"] == "owner"
    assert detail.json()["owner_user_id"] == successor["id"]

    members = client.get(f"/api/v1/universes/{universe_id}/members").json()
    by_user = {member["user_id"]: member["role"] for member in members}
    assert by_user[owner["id"]] == "admin"
    assert by_user[successor["id"]] == "owner"


def test_archived_universe_is_read_only_until_unarchived(open_client: TestClient):
    client = open_client
    register_user(client, "owner_archive@example.com", "Owner")
    universe_id = create_universe(client, "Archive Realm")

    assert client.post(f"/api/v1/universes/{universe_id}/archive").status_code == 200

    blocked_update = client.patch(
        f"/api/v1/universes/{universe_id}", json={"name": "Should Fail"}
    )
    assert blocked_update.status_code == 409
    assert blocked_update.json()["error"]["code"] == "universe_archived"

    blocked_entity = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "character", "title": "No One"},
    )
    assert blocked_entity.status_code == 409
    assert blocked_entity.json()["error"]["code"] == "universe_archived"

    readable = client.get(f"/api/v1/universes/{universe_id}")
    assert readable.status_code == 200
    assert readable.json()["status"] == "archived"

    restored = client.post(f"/api/v1/universes/{universe_id}/unarchive")
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"

    allowed = client.patch(
        f"/api/v1/universes/{universe_id}", json={"name": "Restored Realm"}
    )
    assert allowed.status_code == 200
    assert allowed.json()["name"] == "Restored Realm"


def test_mutations_require_a_valid_csrf_token(open_client: TestClient):
    client = open_client
    register_user(client, "owner_csrf@example.com", "Owner")

    rejected = client.post(
        "/api/v1/universes",
        json={"name": "CSRF Realm"},
        headers={"x-csrf-token": "not-the-token"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "csrf_rejected"

    accepted = client.post("/api/v1/universes", json={"name": "CSRF Realm"})
    assert accepted.status_code == 201


def test_audit_records_use_sha256_state_fingerprints(open_client: TestClient):
    client = open_client
    register_user(client, "owner_audit@example.com", "Owner")
    universe_id = create_universe(client, "Audit Realm")
    assert (
        client.patch(
            f"/api/v1/universes/{universe_id}",
            json={"description": "A revised description"},
        ).status_code
        == 200
    )

    logs = client.get(f"/api/v1/universes/{universe_id}/audit-logs").json()
    update = next(log for log in logs if log["action"] == "universe.update")
    assert update["before_hash"] is not None
    assert update["after_hash"] is not None
    assert len(update["before_hash"]) == 64
    assert len(update["after_hash"]) == 64
    assert update["before_hash"] != update["after_hash"]
