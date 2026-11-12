from __future__ import annotations

from fastapi.testclient import TestClient

AUTH_HEADERS = {"Origin": "http://testserver"}
PASSWORD = "password123456"


def register_user(
    client: TestClient, email: str, display_name: str = "Scholar"
) -> dict:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": display_name, "password": PASSWORD},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str) -> dict:
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
) -> dict:
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
    return member


def create_entity(
    client: TestClient,
    universe_id: str,
    title: str,
    visibility: str = "universe",
    type_key: str = "character",
) -> dict:
    response = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={
            "entity_type_key": type_key,
            "title": title,
            "visibility": visibility,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def visible_titles(client: TestClient, universe_id: str) -> set[str]:
    response = client.get(f"/api/v1/universes/{universe_id}/entities")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == len(payload["items"])
    return {item["title"] for item in payload["items"]}


def test_entity_visibility_enforced_for_viewers_and_editors(open_client: TestClient):
    client = open_client
    owner_email = "visibility_owner@example.com"
    editor_email = "visibility_editor@example.com"
    second_editor_email = "visibility_editor2@example.com"
    viewer_email = "visibility_viewer@example.com"

    register_user(client, owner_email, "Owner")
    universe_id = create_universe(client, "Veiled Realms")
    add_member(client, universe_id, owner_email, editor_email, "editor")
    add_member(client, universe_id, owner_email, second_editor_email, "editor")
    add_member(client, universe_id, owner_email, viewer_email, "viewer")

    login(client, owner_email)
    public = create_entity(client, universe_id, "Public Chronicle")
    restricted = create_entity(client, universe_id, "Restricted Ledger", "restricted")
    private = create_entity(client, universe_id, "Owner Secret", "private")

    login(client, editor_email)
    editor_private = create_entity(client, universe_id, "Editor Secret", "private")
    editor_restricted = create_entity(
        client, universe_id, "Editor Restricted", "restricted"
    )

    login(client, second_editor_email)
    assert visible_titles(client, universe_id) == {
        "Public Chronicle",
        "Restricted Ledger",
        "Editor Restricted",
    }

    # Another editor cannot read or mutate the first editor's private entity.
    hidden_get = client.get(
        f"/api/v1/universes/{universe_id}/entities/{editor_private['id']}"
    )
    assert hidden_get.status_code == 404
    hidden_patch = client.patch(
        f"/api/v1/universes/{universe_id}/entities/{editor_private['id']}",
        json={"title": "Hijacked", "expected_version": 1},
    )
    assert hidden_patch.status_code == 404

    login(client, editor_email)
    assert visible_titles(client, universe_id) == {
        "Public Chronicle",
        "Restricted Ledger",
        "Editor Secret",
        "Editor Restricted",
    }

    login(client, viewer_email)
    assert visible_titles(client, universe_id) == {"Public Chronicle"}

    for hidden in (restricted, private, editor_restricted):
        response = client.get(
            f"/api/v1/universes/{universe_id}/entities/{hidden['id']}"
        )
        assert response.status_code == 404, hidden["title"]


def test_relations_and_graph_hide_invisible_endpoints(open_client: TestClient):
    client = open_client
    owner_email = "graph_owner@example.com"
    editor_email = "graph_editor@example.com"

    register_user(client, owner_email, "Owner")
    universe_id = create_universe(client, "Graph Veil")
    add_member(client, universe_id, owner_email, editor_email, "editor")

    login(client, owner_email)
    public = create_entity(client, universe_id, "Visible Seat")
    hidden = create_entity(client, universe_id, "Hidden Seat", "private")

    relation = client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={
            "source_entity_id": public["id"],
            "relation_type_key": "located_in",
            "target_entity_id": hidden["id"],
        },
    )
    # located_in requires target type "place"; both are characters, so use a
    # permissive custom relation instead.
    if relation.status_code == 400:
        created_type = client.post(
            f"/api/v1/universes/{universe_id}/relation-types",
            json={"key": "linked_to", "label": "Linked to"},
        )
        assert created_type.status_code == 201, created_type.text
        relation = client.post(
            f"/api/v1/universes/{universe_id}/relations",
            json={
                "source_entity_id": public["id"],
                "relation_type_key": "linked_to",
                "target_entity_id": hidden["id"],
            },
        )
    assert relation.status_code == 201, relation.text

    login(client, editor_email)
    relations = client.get(
        f"/api/v1/universes/{universe_id}/entities/{public['id']}/relations"
    )
    assert relations.status_code == 200, relations.text
    assert relations.json() == []

    graph = client.get(f"/api/v1/universes/{universe_id}/graph")
    assert graph.status_code == 200, graph.text
    graph_payload = graph.json()
    assert {node["title"] for node in graph_payload["nodes"]} == {"Visible Seat"}
    assert graph_payload["edges"] == []

    hidden_graph = client.get(
        f"/api/v1/universes/{universe_id}/graph",
        params={"focus_entity_id": hidden["id"]},
    )
    assert hidden_graph.status_code == 404
