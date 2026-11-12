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


def create_universe(client: TestClient, name: str = "Aethelgard"):
    resp = client.post("/api/v1/universes", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_system_and_custom_entity_types(open_client: TestClient):
    client = open_client
    register_user(client, "codex_user1@example.com", "Lorekeeper")
    universe_id = create_universe(client, "Valoria")

    # 1. Listing entity types returns seeded system types
    resp = client.get(f"/api/v1/universes/{universe_id}/entity-types")
    assert resp.status_code == 200
    types = resp.json()
    keys = [t["key"] for t in types]
    assert "character" in keys
    assert "place" in keys
    assert "item" in keys

    # 2. Create custom entity type with schema
    custom_resp = client.post(
        f"/api/v1/universes/{universe_id}/entity-types",
        json={
            "key": "constellation",
            "name": "Constellations",
            "description": "Star patterns and cosmic portents",
            "schema_json": {
                "season": {"type": "enum", "options": ["Spring", "Summer", "Autumn", "Winter"]},
                "magnitude": {"type": "number"},
            },
            "icon": "star",
            "color": "#6d597a",
        },
    )
    assert custom_resp.status_code == 201
    custom_type = custom_resp.json()
    assert custom_type["key"] == "constellation"
    assert custom_type["name"] == "Constellations"


def test_entity_crud_slugs_and_optimistic_concurrency(open_client: TestClient):
    client = open_client
    register_user(client, "codex_author@example.com", "Chronicler")
    universe_id = create_universe(client, "Solaria")

    # Create entity
    create_resp = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={
            "entity_type_key": "character",
            "title": "Aurelius the Sunward",
            "summary": "High Priest of the Radiant Dawn",
            "custom_fields": {"titles": ["Archon", "Keeper of Dawn"], "rank": 5},
            "tags": ["priest", "solar", "canon"],
        },
    )
    assert create_resp.status_code == 201
    entity = create_resp.json()
    entity_id = entity["id"]
    assert entity["title"] == "Aurelius the Sunward"
    assert entity["slug"] == "aurelius-the-sunward"
    assert entity["version"] == 1
    assert "priest" in entity["tags"]

    # Slug collision auto-resolution
    dupe_resp = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={
            "entity_type_key": "character",
            "title": "Aurelius the Sunward",
            "summary": "A duplicate entry",
        },
    )
    assert dupe_resp.status_code == 201
    assert dupe_resp.json()["slug"] == "aurelius-the-sunward-1"

    # Optimistic concurrency conflict (wrong expected_version)
    conflict_resp = client.patch(
        f"/api/v1/universes/{universe_id}/entities/{entity_id}",
        json={
            "title": "Aurelius the Ascended",
            "expected_version": 99,  # Stale version
        },
    )
    assert conflict_resp.status_code == 409
    assert conflict_resp.json()["error"]["code"] == "version_conflict"

    # Successful update increments version
    update_resp = client.patch(
        f"/api/v1/universes/{universe_id}/entities/{entity_id}",
        json={
            "title": "Aurelius the Ascended",
            "expected_version": 1,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["title"] == "Aurelius the Ascended"
    assert updated["version"] == 2

    # Soft delete and restore
    del_resp = client.delete(f"/api/v1/universes/{universe_id}/entities/{entity_id}")
    assert del_resp.status_code == 204

    # Deleted entity is omitted from normal list
    list_resp = client.get(f"/api/v1/universes/{universe_id}/entities")
    ids = [e["id"] for e in list_resp.json()["items"]]
    assert entity_id not in ids

    # Restore
    rest_resp = client.post(f"/api/v1/universes/{universe_id}/entities/{entity_id}/restore")
    assert rest_resp.status_code == 200
    assert rest_resp.json()["id"] == entity_id


def test_relations_and_cross_universe_rejection(open_client: TestClient):
    client = open_client
    register_user(client, "rel_user@example.com", "Relation Architect")
    uni_a = create_universe(client, "Kingdom A")
    uni_b = create_universe(client, "Empire B")

    # Entities in Universe A
    char_a = client.post(
        f"/api/v1/universes/{uni_a}/entities",
        json={"entity_type_key": "character", "title": "King Edward"},
    ).json()

    place_a = client.post(
        f"/api/v1/universes/{uni_a}/entities",
        json={"entity_type_key": "place", "title": "Royal Citadel"},
    ).json()

    # Entity in Universe B
    place_b = client.post(
        f"/api/v1/universes/{uni_b}/entities",
        json={"entity_type_key": "place", "title": "Foreign Fortress"},
    ).json()

    # 1. Valid relation within Universe A
    rel_resp = client.post(
        f"/api/v1/universes/{uni_a}/relations",
        json={
            "source_entity_id": char_a["id"],
            "relation_type_key": "located_in",
            "target_entity_id": place_a["id"],
        },
    )
    assert rel_resp.status_code == 201
    rel = rel_resp.json()
    assert rel["relation_type_key"] == "located_in"
    relation_id = rel["id"]

    # 2. Check entity relations endpoint
    get_rel = client.get(f"/api/v1/universes/{uni_a}/entities/{char_a['id']}/relations")
    assert get_rel.status_code == 200
    assert len(get_rel.json()) == 1

    # 3. Cross-universe relation attempt MUST fail with 400
    cross_resp = client.post(
        f"/api/v1/universes/{uni_a}/relations",
        json={
            "source_entity_id": char_a["id"],
            "relation_type_key": "located_in",
            "target_entity_id": place_b["id"],  # In Universe B!
        },
    )
    assert cross_resp.status_code == 400
    assert "cross-universe" in cross_resp.json()["error"]["message"].lower()

    # 4. Incompatible source type for relation constraint
    # "located_in" allowed_source_types = ["place", "organization", "character"]
    item_a = client.post(
        f"/api/v1/universes/{uni_a}/entities",
        json={"entity_type_key": "item", "title": "Cursed Ring"},
    ).json()
    incompat_resp = client.post(
        f"/api/v1/universes/{uni_a}/relations",
        json={
            "source_entity_id": item_a["id"],  # item not allowed as source of located_in
            "relation_type_key": "located_in",
            "target_entity_id": place_a["id"],
        },
    )
    assert incompat_resp.status_code == 400
    assert incompat_resp.json()["error"]["code"] == "type_constraint_violation"

    # 5. Delete relation
    del_rel_resp = client.delete(f"/api/v1/universes/{uni_a}/relations/{relation_id}")
    assert del_rel_resp.status_code == 204


def test_nexus_graph_api(open_client: TestClient):
    client = open_client
    register_user(client, "graph_user@example.com", "Graph Master")
    universe_id = create_universe(client, "Graphland")

    c1 = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "character", "title": "Node Alpha"},
    ).json()
    c2 = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "character", "title": "Node Beta"},
    ).json()
    c3 = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "character", "title": "Node Gamma"},
    ).json()

    # c1 allied_with c2; c2 allied_with c3
    client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={"source_entity_id": c1["id"], "relation_type_key": "allied_with", "target_entity_id": c2["id"]},
    )
    client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={"source_entity_id": c2["id"], "relation_type_key": "allied_with", "target_entity_id": c3["id"]},
    )

    # Full graph
    graph_resp = client.get(f"/api/v1/universes/{universe_id}/graph")
    assert graph_resp.status_code == 200
    g = graph_resp.json()
    assert len(g["nodes"]) == 3
    assert len(g["edges"]) == 2

    # Focus graph with depth=1 from c1 should reach c2 but not c3
    focus_resp = client.get(
        f"/api/v1/universes/{universe_id}/graph",
        params={"focus_entity_id": c1["id"], "depth": 1},
    )
    assert focus_resp.status_code == 200
    fg = focus_resp.json()
    node_ids = [n["id"] for n in fg["nodes"]]
    assert str(c1["id"]) in node_ids
    assert str(c2["id"]) in node_ids
    assert str(c3["id"]) not in node_ids
