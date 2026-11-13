from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.core.config import Settings
from backend.core.models import Base
from backend.main import create_app
from backend.modules.exports.bundle import render_checksums, sha256_hex
from backend.modules.identity.service import _rate_limiter
from backend.tests.conftest import CsrfTestClient

AUTH_HEADERS = {"Origin": "http://testserver"}
PASSWORD = "password123456"


@pytest.fixture
def client(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        registration_mode="open",
        cookie_secure=False,
        session_ttl_days=30,
        auth_rate_limit=1000,
        auth_rate_window_seconds=60,
        collaboration_ticket_secret="test-collaboration-secret",
        media_root=str(tmp_path / "media"),
        max_asset_bytes=1_048_576,
        max_archive_bytes=5_242_880,
    )
    _rate_limiter.clear()
    application = create_app(settings=settings, engine=engine)
    with CsrfTestClient(application) as test_client:
        yield test_client
    engine.dispose()


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


def create_universe(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/universes", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def seed_universe(client: TestClient, universe_id: str) -> dict:
    """Populate a universe with one entity, one document, and one map."""

    entity_type = client.get(f"/api/v1/universes/{universe_id}/entity-types").json()
    character_type = next(t for t in entity_type if t["key"] == "character")
    entity = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={
            "entity_type_key": "character",
            "title": "Mira Vale",
            "summary": "A cartographer of drowned coasts.",
            "tags": ["protagonist", "explorer"],
            "custom_fields": {},
        },
    )
    assert entity.status_code == 201, entity.text
    document = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={
            "title": "The Salt Road",
            "document_type": "chapter",
            "content_json": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "She walked the salt road."}],
                    }
                ],
            },
        },
    )
    assert document.status_code == 201, document.text
    map_response = client.post(
        f"/api/v1/universes/{universe_id}/maps",
        json={"title": "Drowned Coast", "width": 800, "height": 600},
    )
    assert map_response.status_code == 201, map_response.text
    map_id = map_response.json()["id"]
    marker = client.post(
        f"/api/v1/universes/{universe_id}/maps/{map_id}/markers",
        json={"title": "Mira's Landing", "x_norm": 0.4, "y_norm": 0.6},
    )
    assert marker.status_code == 201, marker.text
    return {
        "entity_id": entity.json()["id"],
        "entity_type_id": character_type["id"],
        "document_id": document.json()["id"],
        "map_id": map_id,
    }


def export_bundle(client: TestClient, universe_id: str) -> bytes:
    response = client.post(f"/api/v1/universes/{universe_id}/exports")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    return response.content


def upload_archive(client: TestClient, url: str, payload: bytes, filename: str = "bundle.zip"):
    return client.post(url, files={"file": (filename, payload, "application/zip")})


def invite_and_accept(client: TestClient, universe_id: str, email: str, role: str) -> None:
    invite = client.post(
        f"/api/v1/universes/{universe_id}/invitations",
        json={"email": email, "role": role},
    )
    assert invite.status_code == 201, invite.text
    token = invite.json()["invitation_token"]
    register(client, email)
    accept = client.post(f"/api/v1/invitations/{token}/accept")
    assert accept.status_code == 200, accept.text


# -----------------------------------------------------------------------------
# Export
# -----------------------------------------------------------------------------

def test_export_produces_portable_bundle_with_manifest_and_checksums(client: TestClient):
    register(client, "exporter@example.com")
    universe_id = create_universe(client, "Export World")
    seeded = seed_universe(client, universe_id)

    payload = export_bundle(client, universe_id)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "universe.json" in names
        assert "checksums.sha256" in names
        assert "entities/index.json" in names
        assert "documents/index.json" in names
        assert "maps/maps.json" in names

        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "worldweave-export"
        assert manifest["schema_version"] == 1
        assert manifest["counts"]["entities"] == 1
        assert manifest["counts"]["documents"] == 1
        assert manifest["counts"]["maps"] == 1

        checksums = {}
        for line in archive.read("checksums.sha256").decode().splitlines():
            digest, name = line.split("  ", 1)
            checksums[name] = digest
        for name, digest in checksums.items():
            assert sha256_hex(archive.read(name)) == digest

        entity_md = next(n for n in names if n.startswith("entities/character/"))
        markdown = archive.read(entity_md).decode()
        assert markdown.startswith("---")
        assert "worldweave_id:" in markdown
        assert "Mira Vale" in markdown

        entities = json.loads(archive.read("entities/index.json"))["items"]
        assert entities[0]["id"] == seeded["entity_id"]
        assert entities[0]["tags"] == ["explorer", "protagonist"]


def test_export_requires_elevated_role(client: TestClient):
    register(client, "owner@example.com")
    universe_id = create_universe(client, "Guarded World")
    invite_and_accept(client, universe_id, "viewer@example.com", "viewer")
    assert client.post(f"/api/v1/universes/{universe_id}/exports").status_code == 403


def test_export_includes_referenced_assets(client: TestClient):
    register(client, "asset-exporter@example.com")
    universe_id = create_universe(client, "Asset Export World")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (2).to_bytes(4, "big") + (3).to_bytes(4, "big")
    upload = client.post(
        f"/api/v1/universes/{universe_id}/assets",
        files={"file": ("map.png", png, "image/png")},
    )
    assert upload.status_code == 201, upload.text
    asset_id = upload.json()["id"]
    created_map = client.post(
        f"/api/v1/universes/{universe_id}/maps",
        json={"title": "Illustrated", "image_asset_id": asset_id},
    )
    assert created_map.status_code == 201, created_map.text

    payload = export_bundle(client, universe_id)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["counts"]["assets"] == 1
        asset_entries = [n for n in archive.namelist() if n.startswith("assets/") and n.endswith(".png")]
        assert len(asset_entries) == 1
        assert archive.read(asset_entries[0]) == png
        records = json.loads(archive.read("assets/assets.json"))["items"]
        assert records[0]["checksum_sha256"] == hashlib.sha256(png).hexdigest()


# -----------------------------------------------------------------------------
# Import validation
# -----------------------------------------------------------------------------

def test_validate_reports_planned_creates_without_writing(client: TestClient):
    register(client, "roundtrip@example.com")
    source_id = create_universe(client, "Source World")
    seed_universe(client, source_id)
    payload = export_bundle(client, source_id)

    target_id = create_universe(client, "Target World")
    response = upload_archive(client, f"/api/v1/universes/{target_id}/imports/validate", payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["source_universe_name"] == "Source World"
    assert body["report"]["counts"]["entity"]["create"] == 1
    assert body["report"]["counts"]["document"]["create"] == 1

    # Nothing should be written during validation.
    assert client.get(f"/api/v1/universes/{target_id}/entities").json()["total"] == 0
    assert client.get(f"/api/v1/universes/{target_id}/documents").json()["total"] == 0


def test_round_trip_into_same_universe_preserves_ids(client: TestClient):
    register(client, "sametrip@example.com")
    universe_id = create_universe(client, "Home World")
    seeded = seed_universe(client, universe_id)
    payload = export_bundle(client, universe_id)

    response = upload_archive(
        client,
        f"/api/v1/universes/{universe_id}/imports?conflict_policy=overwrite",
        payload,
    )
    assert response.status_code == 201, response.text
    assert response.json()["report_json"]["counts"]["entity"]["update"] == 1

    entities = client.get(f"/api/v1/universes/{universe_id}/entities").json()
    assert entities["total"] == 1
    assert entities["items"][0]["id"] == seeded["entity_id"]
    documents = client.get(f"/api/v1/universes/{universe_id}/documents").json()
    assert documents["total"] == 1
    assert documents["items"][0]["id"] == seeded["document_id"]


def test_clone_into_new_universe_remaps_ids_and_keeps_graph_consistent(client: TestClient):
    register(client, "clone@example.com")
    source_id = create_universe(client, "Origin World")
    seeded = seed_universe(client, source_id)
    second = client.post(
        f"/api/v1/universes/{source_id}/entities",
        json={"entity_type_key": "character", "title": "Kael", "custom_fields": {}},
    )
    assert second.status_code == 201, second.text
    relation = client.post(
        f"/api/v1/universes/{source_id}/relations",
        json={
            "source_entity_id": seeded["entity_id"],
            "relation_type_key": "allied_with",
            "target_entity_id": second.json()["id"],
        },
    )
    assert relation.status_code == 201, relation.text
    payload = export_bundle(client, source_id)

    target_id = create_universe(client, "Clone World")
    response = upload_archive(
        client, f"/api/v1/universes/{target_id}/imports?conflict_policy=skip", payload
    )
    assert response.status_code == 201, response.text
    assert response.json()["source_universe_id"] == source_id

    entities = client.get(f"/api/v1/universes/{target_id}/entities").json()
    assert entities["total"] == 2
    cloned_ids = {item["id"] for item in entities["items"]}
    # Fresh ids: none collide with the source universe.
    assert seeded["entity_id"] not in cloned_ids
    assert second.json()["id"] not in cloned_ids

    # The relation must reference two entities that exist in the clone.
    for item in entities["items"]:
        if item["title"] == "Mira Vale":
            rels = client.get(
                f"/api/v1/universes/{target_id}/entities/{item['id']}/relations"
            ).json()
            assert len(rels) == 1
            assert rels[0]["target_entity_id"] in cloned_ids
    # The source universe is untouched.
    assert client.get(f"/api/v1/universes/{source_id}/entities").json()["total"] == 2


def test_conflict_policy_skip_and_overwrite(client: TestClient):
    register(client, "conflict@example.com")
    universe_id = create_universe(client, "Conflict World")
    seeded = seed_universe(client, universe_id)
    payload = export_bundle(client, universe_id)

    # Re-importing with skip leaves existing records untouched.
    skipped = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports?conflict_policy=skip", payload
    )
    assert skipped.status_code == 201, skipped.text
    assert skipped.json()["report_json"]["counts"]["entity"]["skip"] == 1

    # Overwrite applies the bundle version and bumps the entity version.
    overwrite = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports?conflict_policy=overwrite", payload
    )
    assert overwrite.status_code == 201, overwrite.text
    assert overwrite.json()["report_json"]["counts"]["entity"]["update"] == 1
    entities = client.get(f"/api/v1/universes/{universe_id}/entities").json()
    assert entities["total"] == 1
    assert entities["items"][0]["id"] == seeded["entity_id"]


def test_conflict_policy_fail_blocks_import(client: TestClient):
    register(client, "failpolicy@example.com")
    universe_id = create_universe(client, "Fail World")
    seed_universe(client, universe_id)
    payload = export_bundle(client, universe_id)

    failed = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports?conflict_policy=fail", payload
    )
    assert failed.status_code == 422, failed.text
    assert failed.json()["error"]["code"] == "import_validation_failed"


def test_dry_run_reports_without_persisting(client: TestClient):
    register(client, "dryrun@example.com")
    source_id = create_universe(client, "Dry Source")
    seed_universe(client, source_id)
    payload = export_bundle(client, source_id)

    target_id = create_universe(client, "Dry Target")
    response = upload_archive(
        client, f"/api/v1/universes/{target_id}/imports?dry_run=true", payload
    )
    assert response.status_code == 201, response.text
    assert response.json()["dry_run"] is True
    assert client.get(f"/api/v1/universes/{target_id}/entities").json()["total"] == 0


# -----------------------------------------------------------------------------
# Safety
# -----------------------------------------------------------------------------

def _rekey_universe(payload: bytes, new_universe_id: str) -> bytes:
    """Rewrite universe.json so a bundle claims a different source universe.

    Every other member (including checksums) is preserved, so the archive stays
    internally consistent while presenting foreign ids as its own.
    """

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    universe = json.loads(members["universe.json"])
    universe["id"] = new_universe_id
    members["universe.json"] = json.dumps(universe).encode()
    members.pop("checksums.sha256", None)
    members["checksums.sha256"] = render_checksums(members).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _bundle_with_member(member: str, content: bytes) -> bytes:
    universe = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Crafted",
        "slug": "crafted",
        "schema_version": 1,
    }
    manifest = {
        "format": "worldweave-export",
        "schema_version": 1,
        "exporter_version": "1.0.0",
        "universe_id": universe["id"],
        "universe_name": universe["name"],
        "universe_slug": universe["slug"],
        "exported_at": "2026-01-01T00:00:00+00:00",
        "counts": {},
        "warnings": [],
    }
    files = {
        "manifest.json": json.dumps(manifest).encode(),
        "universe.json": json.dumps(universe).encode(),
        "entities/index.json": json.dumps({"items": []}).encode(),
    }
    files[member] = content
    files["checksums.sha256"] = render_checksums(files).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_import_rejects_non_bundle_archive(client: TestClient):
    register(client, "safety@example.com")
    universe_id = create_universe(client, "Safety World")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", b"hello")
    response = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports/validate", buffer.getvalue()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "archive_missing_member"


def test_import_rejects_checksum_mismatch(client: TestClient):
    register(client, "tamper@example.com")
    universe_id = create_universe(client, "Tamper World")
    payload = bytearray(_bundle_with_member("entities/extra.json", b'{"items": []}'))
    # Corrupt the checksum index so a declared digest no longer matches.
    with zipfile.ZipFile(io.BytesIO(bytes(payload))) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members["checksums.sha256"] = b"0" * 64 + b"  manifest.json\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    response = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports/validate", buffer.getvalue()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "checksum_mismatch"


def test_import_rejects_path_traversal_entry(client: TestClient):
    register(client, "traversal@example.com")
    universe_id = create_universe(client, "Traversal World")
    payload = _bundle_with_member("../escape.md", b"# nope")
    response = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports/validate", payload
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "archive_unsafe_path"


def test_import_rejects_symlink_entry(client: TestClient):
    register(client, "symlink@example.com")
    universe_id = create_universe(client, "Symlink World")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", b"{}")
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777 << 16)
        archive.writestr(info, "/etc/passwd")
    response = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports/validate", buffer.getvalue()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "archive_symlink_rejected"


def test_import_rejects_archive_over_limit(client: TestClient):
    register(client, "oversize@example.com")
    universe_id = create_universe(client, "Oversize World")
    oversized = b"0" * (6 * 1024 * 1024)
    response = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports/validate", oversized
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "archive_too_large"


def test_import_rejects_foreign_id_collision(client: TestClient):
    register(client, "foreign@example.com")
    source_id = create_universe(client, "Foreign Source")
    seeded = seed_universe(client, source_id)
    payload = export_bundle(client, source_id)

    # A crafted bundle that claims a foreign universe but reuses the source id
    # must be rejected, not silently overwrite another universe's records.
    target_id = create_universe(client, "Foreign Target")
    tampered = _rekey_universe(payload, target_id)
    response = upload_archive(
        client, f"/api/v1/universes/{target_id}/imports?conflict_policy=skip", tampered
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "import_validation_failed"
    # The source universe is untouched.
    assert client.get(f"/api/v1/universes/{source_id}/entities").json()["total"] == 1
    source_entity = client.get(f"/api/v1/universes/{source_id}/entities").json()["items"][0]
    assert source_entity["id"] == seeded["entity_id"]


def test_import_requires_permission(client: TestClient):
    register(client, "perm-owner@example.com")
    universe_id = create_universe(client, "Perm World")
    payload = export_bundle(client, universe_id)
    invite_and_accept(client, universe_id, "perm-viewer@example.com", "viewer")
    response = upload_archive(
        client, f"/api/v1/universes/{universe_id}/imports/validate", payload
    )
    assert response.status_code == 403


def test_import_jobs_are_listed(client: TestClient):
    register(client, "jobs@example.com")
    source_id = create_universe(client, "Jobs Source")
    seed_universe(client, source_id)
    payload = export_bundle(client, source_id)
    target_id = create_universe(client, "Jobs Target")
    assert upload_archive(
        client, f"/api/v1/universes/{target_id}/imports", payload
    ).status_code == 201
    jobs = client.get(f"/api/v1/universes/{target_id}/imports").json()
    assert jobs["total"] == 1
    assert jobs["items"][0]["conflict_policy"] == "skip"
