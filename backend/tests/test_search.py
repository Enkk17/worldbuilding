from __future__ import annotations

from fastapi.testclient import TestClient

AUTH_HEADERS = {"Origin": "http://testserver"}
PASSWORD = "password123456"


def register(client: TestClient, email: str) -> None:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": email.split("@")[0], "password": PASSWORD},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text


def login(client: TestClient, email: str) -> None:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text


def make_universe(client: TestClient, name: str = "Search World") -> str:
    response = client.post("/api/v1/universes", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def invite_member(client: TestClient, universe_id: str, owner: str, email: str, role: str = "viewer") -> None:
    login(client, owner)
    invitation = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": email, "role": role},
    )
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()["invitation_token"]
    register(client, email)
    accepted = client.post(f"/api/v1/invitations/{token}/accept")
    assert accepted.status_code == 200, accepted.text
    login(client, email)


def test_unified_search_finds_entities_documents_and_timeline_events(open_client: TestClient):
    client = open_client
    register(client, "search-owner@example.com")
    universe_id = make_universe(client)

    entity = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "place", "title": "Moonlit Harbor", "summary": "A silver port"},
    )
    assert entity.status_code == 201, entity.text
    document = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={
            "title": "Chronicle of the Tide",
            "document_type": "chapter",
            "content_json": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "The moonlit fleets returned."}]}]},
        },
    )
    assert document.status_code == 201, document.text
    calendar = client.post(
        f"/api/v1/universes/{universe_id}/calendars",
        json={"name": "Tide Calendar", "config_json": {"months": [{"name": "Tide", "days": 30}]}},
    )
    assert calendar.status_code == 201, calendar.text
    event = client.post(
        f"/api/v1/universes/{universe_id}/timeline-events",
        json={
            "calendar_id": calendar.json()["id"],
            "title": "Moonlit crossing",
            "description": "A fleet crossed the moonlit sea.",
            "start_date_json": {"year": 2, "month": 1, "day": 5},
            "linked_entity_id": entity.json()["id"],
            "linked_document_id": document.json()["id"],
        },
    )
    assert event.status_code == 201, event.text

    response = client.get(f"/api/v1/universes/{universe_id}/search", params={"q": "moonlit"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert {result["kind"] for result in payload["items"]} == {"entity", "document", "timeline_event"}
    assert all(result["highlight_start"] < result["highlight_end"] for result in payload["items"])
    assert all(result["href"].startswith(f"/universes/{universe_id}") for result in payload["items"])

    filtered = client.get(
        f"/api/v1/universes/{universe_id}/search",
        params=[("q", "moonlit"), ("types", "entity"), ("types", "document"), ("limit", "1")],
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 2
    assert len(filtered.json()["items"]) == 1
    assert filtered.json()["items"][0]["kind"] in {"entity", "document"}
    assert client.get(f"/api/v1/universes/{universe_id}/search", params={"q": "moonlit", "offset": 1, "limit": 1}).json()["items"][0]["id"] != payload["items"][0]["id"]


def test_search_respects_private_visibility_and_tenant_isolation(open_client: TestClient):
    client = open_client
    owner = "visibility-owner@example.com"
    register(client, owner)
    universe_id = make_universe(client, "Visibility Search")
    public = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "character", "title": "Public Aurora"},
    )
    private = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "character", "title": "Secret Aurora", "visibility": "private"},
    )
    assert public.status_code == private.status_code == 201

    invite_member(client, universe_id, owner, "search-viewer@example.com", "viewer")
    visible = client.get(f"/api/v1/universes/{universe_id}/search", params={"q": "aurora", "types": "entity"})
    assert visible.status_code == 200
    assert {result["id"] for result in visible.json()["items"]} == {public.json()["id"]}

    register(client, "search-outsider@example.com")
    other_universe = make_universe(client, "Other Search World")
    assert client.get(f"/api/v1/universes/{universe_id}/search", params={"q": "aurora"}).status_code == 404
    assert client.get(f"/api/v1/universes/{other_universe}/search", params={"q": "aurora"}).json()["total"] == 0


def test_search_validation_and_like_wildcards_are_safe(open_client: TestClient):
    client = open_client
    register(client, "search-validation@example.com")
    universe_id = make_universe(client, "Search Validation")
    short = client.get(f"/api/v1/universes/{universe_id}/search", params={"q": "x"})
    assert short.status_code == 422
    invalid_type = client.get(f"/api/v1/universes/{universe_id}/search", params=[("q", "safe query"), ("types", "secrets")])
    assert invalid_type.status_code == 422
    wildcard = client.get(f"/api/v1/universes/{universe_id}/search", params={"q": "%_"})
    assert wildcard.status_code == 200
    assert wildcard.json()["total"] == 0
