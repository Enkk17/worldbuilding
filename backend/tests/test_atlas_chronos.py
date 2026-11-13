from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

AUTH_HEADERS = {"Origin": "http://testserver"}
PASSWORD = "password123456"


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


def create_universe(client: TestClient, name: str = "M6 World") -> str:
    response = client.post("/api/v1/universes", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_calendar(client: TestClient, universe_id: str) -> dict:
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


def test_atlas_map_marker_region_crud_and_normalized_coordinates(open_client: TestClient):
    client = open_client
    register(client, "atlas-owner@example.com")
    universe_id = create_universe(client)

    created = client.post(
        f"/api/v1/universes/{universe_id}/maps",
        json={"title": "The Known Lands", "width": 2400, "height": 1200},
    )
    assert created.status_code == 201, created.text
    map_record = created.json()
    map_id = map_record["id"]
    assert map_record["coordinate_system"] == "normalized"
    assert map_record["version"] == 1

    marker = client.post(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/markers",
        json={"title": "Harbor", "x_norm": 0.25, "y_norm": 0.75},
    )
    assert marker.status_code == 201, marker.text
    marker_data = marker.json()
    assert marker_data["x_norm"] == 0.25
    assert marker_data["y_norm"] == 0.75

    invalid = client.post(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/markers",
        json={"title": "Outside map", "x_norm": 1.01, "y_norm": 0.5},
    )
    assert invalid.status_code == 422

    updated = client.patch(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/markers/{marker_data['id']}",
        json={"x_norm": 0.5, "expected_version": 1},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    stale = client.patch(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/markers/{marker_data['id']}",
        json={"title": "Stale write", "expected_version": 1},
    )
    assert stale.status_code == 409

    polygon = {"type": "polygon", "points": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.5, "y": 0.8}]}
    region = client.post(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/regions",
        json={"title": "The Vale", "geometry_json": polygon},
    )
    assert region.status_code == 201, region.text
    region_id = region.json()["id"]
    changed = client.patch(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/regions/{region_id}",
        json={"title": "The Green Vale", "expected_version": 1},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert changed.json()["title"] == "The Green Vale"
    assert client.delete(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/regions/{region_id}"
    ).status_code == 204

    listing = client.get(f"/api/v1/universes/{universe_id}/maps")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert client.patch(
        f"/api/v1/universes/{universe_id}/maps/{map_id}",
        json={"title": "Updated atlas", "expected_version": 1},
    ).json()["version"] == 2


def test_atlas_tenant_isolation_and_role_write_rejection(open_client: TestClient):
    client = open_client
    register(client, "atlas-a@example.com")
    universe_a = create_universe(client, "Atlas A")
    map_response = client.post(
        f"/api/v1/universes/{universe_a}/maps", json={"title": "Secret map"}
    )
    assert map_response.status_code == 201
    map_id = map_response.json()["id"]

    register(client, "atlas-b@example.com")
    universe_b = create_universe(client, "Atlas B")
    assert client.get(f"/api/v1/universes/{universe_b}/maps/{map_id}").status_code == 404
    assert client.get(f"/api/v1/universes/{universe_b}/maps").json()["total"] == 0


def test_asset_upload_checksum_download_and_universe_scoping(open_client: TestClient):
    client = open_client
    register(client, "asset-owner@example.com")
    universe_id = create_universe(client, "Asset World")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (2).to_bytes(4, "big") + (3).to_bytes(4, "big")
    response = client.post(
        f"/api/v1/universes/{universe_id}/assets",
        files={"file": ("../world.png", png, "image/png")},
    )
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["original_filename"] == "world.png"
    assert asset["checksum_sha256"] == hashlib.sha256(png).hexdigest()
    assert (asset["width"], asset["height"]) == (2, 3)
    download = client.get(asset["download_path"])
    assert download.status_code == 200
    assert download.content == png

    register(client, "asset-other@example.com")
    create_universe(client, "Other Asset World")
    assert client.get(asset["download_path"]).status_code == 404
    assert client.get(
        f"/api/v1/universes/{universe_id}/assets/{asset['id']}"
    ).status_code == 404


def test_custom_calendar_leap_rules_precision_and_ranges(open_client: TestClient):
    client = open_client
    register(client, "chronos-owner@example.com")
    universe_id = create_universe(client, "Chronos World")
    calendar = create_calendar(client, universe_id)
    calendar_id = calendar["id"]

    def create_event(title: str, start: dict, precision: str = "day", **extra):
        return client.post(
            f"/api/v1/universes/{universe_id}/timeline-events",
            json={
                "calendar_id": calendar_id,
                "title": title,
                "start_date_json": start,
                "date_precision": precision,
                **extra,
            },
        )

    ordinary = create_event("First day", {"year": 1, "month": 2, "day": 30})
    leap = create_event("Intercalary night", {"year": 4, "month": 2, "day": 32})
    assert ordinary.status_code == 201, ordinary.text
    assert leap.status_code == 201, leap.text
    assert leap.json()["start_day_index"] - ordinary.json()["start_day_index"] == 3 * 90 + 2

    not_leap = create_event("Invalid extra day", {"year": 1, "month": 2, "day": 32})
    assert not_leap.status_code == 422

    year = create_event("Year-long event", {"year": 4}, "year")
    assert year.status_code == 201, year.text
    assert year.json()["end_day_index"] - year.json()["start_day_index"] == 91

    month = create_event("Monthly festival", {"year": 4, "month": 2}, "month")
    assert month.status_code == 201, month.text
    assert month.json()["end_day_index"] - month.json()["start_day_index"] == 31

    approximate = create_event(
        "Uncertain omen", {"year": 4, "month": 1, "day": 1}, "approximate",
        uncertainty_json={"before_days": 2, "after_days": 5},
    )
    assert approximate.status_code == 201, approximate.text
    assert approximate.json()["end_day_index"] - approximate.json()["start_day_index"] == 7

    ranged = create_event(
        "The migration", {"year": 5, "month": 1, "day": 1}, "range",
        end_date_json={"year": 5, "month": 1, "day": 10},
    )
    assert ranged.status_code == 201, ranged.text
    assert ranged.json()["end_day_index"] - ranged.json()["start_day_index"] == 9

    inverted = create_event(
        "Impossible range", {"year": 5, "month": 2, "day": 1}, "range",
        end_date_json={"year": 5, "month": 1, "day": 1},
    )
    assert inverted.status_code == 422

    update = client.patch(
        f"/api/v1/universes/{universe_id}/timeline-events/{ordinary.json()['id']}",
        json={"title": "First dawn", "expected_version": 1},
    )
    assert update.status_code == 200, update.text
    assert update.json()["version"] == 2
    assert client.get(
        f"/api/v1/universes/{universe_id}/timeline-events",
        params={"calendar_id": calendar_id, "q": "migration"},
    ).json()["total"] == 1


def test_calendar_configuration_is_immutable_after_events_and_invalid_rules_rejected(open_client: TestClient):
    client = open_client
    register(client, "calendar-rules@example.com")
    universe_id = create_universe(client, "Calendar Rules")
    invalid = client.post(
        f"/api/v1/universes/{universe_id}/calendars",
        json={"name": "Bad", "config_json": {"months": [{"name": "A", "days": 10}], "leap_rules": [{"every_years": 4, "month": 2}]}},
    )
    assert invalid.status_code == 422
    calendar = create_calendar(client, universe_id)
    event = client.post(
        f"/api/v1/universes/{universe_id}/timeline-events",
        json={"calendar_id": calendar["id"], "title": "An event", "start_date_json": {"year": 1, "month": 1, "day": 1}},
    )
    assert event.status_code == 201
    locked = client.patch(
        f"/api/v1/universes/{universe_id}/calendars/{calendar['id']}",
        json={"config_json": {"months": [{"name": "New", "days": 99}]}, "expected_version": 1},
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "calendar_in_use"


def test_calendar_big_day_indices_do_not_overflow_signed_32_bits(open_client: TestClient):
    client = open_client
    register(client, "calendar-bigint@example.com")
    universe_id = create_universe(client, "Deep Time")
    calendar = client.post(
        f"/api/v1/universes/{universe_id}/calendars",
        json={"name": "Deep", "config_json": {"months": [{"name": "Aeon", "days": 1000}]}},
    )
    assert calendar.status_code == 201, calendar.text
    event = client.post(
        f"/api/v1/universes/{universe_id}/timeline-events",
        json={"calendar_id": calendar.json()["id"], "title": "Far future", "start_date_json": {"year": 1_000_000, "month": 1, "day": 1}},
    )
    assert event.status_code == 201, event.text
    assert event.json()["start_day_index"] == 1_000_000_000


def test_map_regions_and_custom_leap_dates_have_api_contract(open_client: TestClient):
    assert open_client.get("/api/openapi.json").status_code == 200
    schema = open_client.get("/api/openapi.json").json()
    assert "/api/v1/universes/{universe_id}/maps/{map_id}/regions/{region_id}" in schema["paths"]
    assert "MapRegionUpdate" in schema["components"]["schemas"]
    assert "leap_rules" in schema["components"]["schemas"]["CalendarConfiguration"]["properties"]
