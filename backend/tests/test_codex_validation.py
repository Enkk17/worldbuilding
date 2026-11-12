from __future__ import annotations

from fastapi.testclient import TestClient

AUTH_HEADERS = {"Origin": "http://testserver"}


def register(client: TestClient, email: str = "validator@example.com") -> dict:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Validator",
            "password": "password123456",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_universe(client: TestClient, name: str = "Validation Realm") -> str:
    response = client.post("/api/v1/universes", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_entity(
    client: TestClient,
    universe_id: str,
    type_key: str,
    title: str,
    **extra,
) -> dict:
    payload = {"entity_type_key": type_key, "title": title, **extra}
    response = client.post(
        f"/api/v1/universes/{universe_id}/entities", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_custom_field_schema_and_value_validation(open_client: TestClient):
    client = open_client
    register(client)
    universe_id = create_universe(client)

    schema = {
        "fields": [
            {"key": "epithet", "label": "Epithet", "type": "text", "required": True},
            {"key": "age", "label": "Age", "type": "number"},
            {
                "key": "temperament",
                "label": "Temperament",
                "type": "enum",
                "options": ["Calm", "Fierce"],
            },
            {
                "key": "domains",
                "label": "Domains",
                "type": "multi_enum",
                "options": ["Sea", "Sky", "Stone"],
            },
            {"key": "born", "label": "Born", "type": "date"},
            {"key": "banner", "label": "Banner", "type": "url"},
            {"key": "sworn", "label": "Sworn", "type": "boolean"},
            {
                "key": "liege",
                "label": "Liege",
                "type": "entity_reference",
                "target_entity_type_key": "character",
            },
            {"key": "notes", "label": "Notes", "type": "long_text"},
        ]
    }
    created_type = client.post(
        f"/api/v1/universes/{universe_id}/entity-types",
        json={
            "key": "hero",
            "name": "Heroes",
            "schema_json": schema,
        },
    )
    assert created_type.status_code == 201, created_type.text
    stored = created_type.json()["schema_json"]
    assert stored["epithet"]["required"] is True
    assert stored["temperament"]["options"] == ["Calm", "Fierce"]

    missing_required = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": "hero", "title": "No Epithet"},
    )
    assert missing_required.status_code == 422
    assert missing_required.json()["error"]["code"] == "validation_error"

    invalid_values = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={
            "entity_type_key": "hero",
            "title": "Invalid Hero",
            "custom_fields": {
                "epithet": "The Bold",
                "age": "old",
                "temperament": "Unknown",
                "domains": ["Sea", "Moon"],
                "born": "not-a-date",
                "banner": "javascript:alert(1)",
                "sworn": "yes",
            },
        },
    )
    assert invalid_values.status_code == 422
    codes = {
        field["code"] for field in invalid_values.json()["error"]["details"]["fields"]
    }
    assert {"number_required", "invalid_option", "date_required", "url_required", "boolean_required"} <= codes

    liege = create_entity(client, universe_id, "character", "The Liege")
    valid = create_entity(
        client,
        universe_id,
        "hero",
        "Valid Hero",
        custom_fields={
            "epithet": "  The Bold  ",
            "age": 42,
            "temperament": "Calm",
            "domains": ["Sea", "Sea", "Sky"],
            "born": "1990-04-12",
            "banner": "https://example.com/banner.png",
            "sworn": True,
            "liege": liege["id"],
            "notes": "A long field can contain paragraphs.",
        },
    )
    assert valid["custom_fields"]["epithet"] == "The Bold"
    assert valid["custom_fields"]["domains"] == ["Sea", "Sky"]

    unknown_field = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={
            "entity_type_key": "hero",
            "title": "Unknown Field",
            "custom_fields": {"epithet": "The Bold", "forbidden": "value"},
        },
    )
    assert unknown_field.status_code == 422
    assert unknown_field.json()["error"]["details"]["fields"][0]["code"] == "unknown_field"

    wrong_type = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={
            "entity_type_key": "hero",
            "title": "Wrong Reference",
            "custom_fields": {"epithet": "The Bold", "liege": universe_id},
        },
    )
    assert wrong_type.status_code == 422


def test_entity_reference_cross_universe_and_type_are_rejected(open_client: TestClient):
    client = open_client
    register(client, "ref_validator@example.com")
    universe_a = create_universe(client, "Reference A")
    universe_b = create_universe(client, "Reference B")

    client.post(
        f"/api/v1/universes/{universe_a}/entity-types",
        json={
            "key": "oath",
            "name": "Oaths",
            "schema_json": {
                "sworn_to": {
                    "type": "entity_reference",
                    "target_entity_type_key": "character",
                }
            },
        },
    )
    foreign_character = create_entity(
        client, universe_b, "character", "Foreign Character"
    )
    local_place = create_entity(client, universe_a, "place", "Local Place")

    cross_universe = client.post(
        f"/api/v1/universes/{universe_a}/entities",
        json={
            "entity_type_key": "oath",
            "title": "Foreign Oath",
            "custom_fields": {"sworn_to": foreign_character["id"]},
        },
    )
    assert cross_universe.status_code == 422
    assert cross_universe.json()["error"]["details"]["fields"][0]["code"] == "entity_not_found"

    wrong_type = client.post(
        f"/api/v1/universes/{universe_a}/entities",
        json={
            "entity_type_key": "oath",
            "title": "Wrong Oath",
            "custom_fields": {"sworn_to": local_place["id"]},
        },
    )
    assert wrong_type.status_code == 422
    assert wrong_type.json()["error"]["details"]["fields"][0]["code"] == "entity_type_mismatch"


def test_custom_field_schema_rejects_invalid_definitions(open_client: TestClient):
    client = open_client
    register(client, "schema_validator@example.com")
    universe_id = create_universe(client, "Schema Realm")

    unsupported = client.post(
        f"/api/v1/universes/{universe_id}/entity-types",
        json={
            "key": "bad",
            "name": "Bad",
            "schema_json": {"field": {"type": "formula"}},
        },
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["error"]["details"]["fields"][0]["code"] == "unsupported_type"

    no_options = client.post(
        f"/api/v1/universes/{universe_id}/entity-types",
        json={
            "key": "bad_enum",
            "name": "Bad Enum",
            "schema_json": {"field": {"type": "enum"}},
        },
    )
    assert no_options.status_code == 422
    assert no_options.json()["error"]["details"]["fields"][0]["code"] == "options_required"

    unknown_attribute = client.post(
        f"/api/v1/universes/{universe_id}/entity-types",
        json={
            "key": "bad_attr",
            "name": "Bad Attr",
            "schema_json": {
                "field": {"type": "text", "executable": "process.exit()"}
            },
        },
    )
    assert unknown_attribute.status_code == 422
    assert unknown_attribute.json()["error"]["details"]["fields"][0]["code"] == "unknown_attributes"


def test_relation_duplicate_self_and_unknown_type_are_rejected(open_client: TestClient):
    client = open_client
    register(client, "relation_validator@example.com")
    universe_id = create_universe(client, "Relation Realm")
    alice = create_entity(client, universe_id, "character", "Alice")
    bob = create_entity(client, universe_id, "character", "Bob")

    unknown_type = client.post(
        f"/api/v1/universes/{universe_id}/relation-types",
        json={
            "key": "custom_link",
            "label": "Custom Link",
            "allowed_source_types": ["missing_type"],
        },
    )
    assert unknown_type.status_code == 422

    payload = {
        "source_entity_id": alice["id"],
        "relation_type_key": "allied_with",
        "target_entity_id": bob["id"],
    }
    assert (
        client.post(f"/api/v1/universes/{universe_id}/relations", json=payload).status_code
        == 201
    )
    duplicate = client.post(
        f"/api/v1/universes/{universe_id}/relations", json=payload
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "relation_exists"

    reverse = client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={
            "source_entity_id": bob["id"],
            "relation_type_key": "allied_with",
            "target_entity_id": alice["id"],
        },
    )
    assert reverse.status_code == 409

    self_relation = client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={
            "source_entity_id": alice["id"],
            "relation_type_key": "parent_of",
            "target_entity_id": alice["id"],
        },
    )
    assert self_relation.status_code == 400
    assert self_relation.json()["error"]["code"] == "self_relation_not_allowed"


def test_entity_pagination_and_graph_filters(open_client: TestClient):
    client = open_client
    register(client, "graph_filters@example.com")
    universe_id = create_universe(client, "Filter Realm")
    a = create_entity(client, universe_id, "character", "Alpha")
    b = create_entity(client, universe_id, "character", "Beta")
    place = create_entity(client, universe_id, "place", "Citadel")

    relation = client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={
            "source_entity_id": a["id"],
            "relation_type_key": "located_in",
            "target_entity_id": place["id"],
        },
    ).json()
    client.post(
        f"/api/v1/universes/{universe_id}/relations",
        json={
            "source_entity_id": b["id"],
            "relation_type_key": "located_in",
            "target_entity_id": place["id"],
        },
    )

    page = client.get(
        f"/api/v1/universes/{universe_id}/entities", params={"limit": 1, "offset": 0}
    )
    assert page.status_code == 200
    assert len(page.json()["items"]) == 1
    assert page.json()["total"] == 3

    by_type = client.get(
        f"/api/v1/universes/{universe_id}/graph",
        params={"type_keys": "character"},
    ).json()
    assert {node["entity_type_key"] for node in by_type["nodes"]} == {"character"}
    assert by_type["edges"] == []

    relation_types = client.get(
        f"/api/v1/universes/{universe_id}/relation-types"
    ).json()
    located_in = next(rt for rt in relation_types if rt["key"] == "located_in")
    filtered = client.get(
        f"/api/v1/universes/{universe_id}/graph",
        params={"relation_type_ids": located_in["id"]},
    ).json()
    assert len(filtered["edges"]) == 2
    assert {edge["id"] for edge in filtered["edges"]} == {
        edge["id"] for edge in client.get(
            f"/api/v1/universes/{universe_id}/graph"
        ).json()["edges"]
    }

    bad_depth = client.get(
        f"/api/v1/universes/{universe_id}/graph", params={"depth": 4}
    )
    assert bad_depth.status_code == 422

    missing_focus = client.get(
        f"/api/v1/universes/{universe_id}/graph",
        params={"focus_entity_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing_focus.status_code == 404

    assert relation["id"]
