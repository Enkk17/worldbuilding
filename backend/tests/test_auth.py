from __future__ import annotations

from dataclasses import replace


def create_account(client, email: str = "writer@example.org"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": "World Weaver",
        },
    )


def test_registration_creates_account_and_hashed_session(client):
    response = create_account(client)

    assert response.status_code == 201
    account = response.json()
    assert account["email"] == "writer@example.org"
    assert account["display_name"] == "World Weaver"
    assert len(account["id"]) == 36
    assert "password" not in account
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(cookie for cookie in cookies if cookie.startswith("ww_session="))
    csrf_cookie = next(cookie for cookie in cookies if cookie.startswith("ww_csrf="))
    assert "httponly" in session_cookie.lower()
    assert "path=/api/v1" in session_cookie.lower()
    assert "path=/" in csrf_cookie.lower()
    assert client.cookies.get("ww_csrf")
    assert client.get("/api/v1/auth/me").json()["id"] == account["id"]


def test_session_logout_requires_csrf_and_revokes_server_record(client):
    assert create_account(client).status_code == 201
    csrf_token = client.cookies.get("ww_csrf")
    assert csrf_token

    denied = client.post("/api/v1/auth/logout")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "csrf_rejected"

    logged_out = client.post(
        "/api/v1/auth/logout",
        headers={"x-csrf-token": csrf_token},
    )
    assert logged_out.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_uses_generic_invalid_credentials_error(client):
    assert create_account(client).status_code == 201
    client.post("/api/v1/auth/logout", headers={"x-csrf-token": client.cookies["ww_csrf"]})

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "writer@example.org", "password": "incorrect-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert "incorrect-password" not in response.text


def test_login_rotates_and_revokes_an_existing_session(client):
    assert create_account(client).status_code == 201
    old_token = client.cookies.get("ww_session")
    assert old_token

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "writer@example.org",
            "password": "correct-horse-battery-staple",
        },
    )

    assert response.status_code == 200
    new_token = client.cookies.get("ww_session")
    assert new_token and new_token != old_token

    client.cookies.set("ww_session", old_token, path="/api/v1")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_registration_is_bootstrap_only_by_default(client):
    assert create_account(client).status_code == 201

    response = create_account(client, email="another@example.org")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "registration_disabled"


def test_duplicate_account_does_not_disclose_private_fields(client):
    client.app.state.settings = replace(
        client.app.state.settings, registration_mode="open"
    )
    assert create_account(client).status_code == 201
    client.post("/api/v1/auth/logout", headers={"x-csrf-token": client.cookies["ww_csrf"]})

    response = create_account(client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_exists"
    assert "password_hash" not in response.text


def test_malformed_registration_is_returned_as_stable_validation_error(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "short", "display_name": ""},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "input" not in response.text.lower()


def test_registration_rejects_a_cross_origin_request(client):
    response = client.post(
        "/api/v1/auth/register",
        headers={"origin": "https://untrusted.example"},
        json={
            "email": "writer@example.org",
            "password": "correct-horse-battery-staple",
            "display_name": "World Weaver",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_rejected"
