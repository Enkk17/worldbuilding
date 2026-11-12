from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from backend.modules.chronicle.markdown import markdown_to_tiptap, tiptap_to_markdown

AUTH_HEADERS = {"Origin": "http://testserver"}
PASSWORD = "password123456"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def register_user(
    client: TestClient, email: str, display_name: str = "Chronicler"
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
    role: str = "viewer",
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
    login(client, owner_email)
    return member


def create_entity(
    client: TestClient, universe_id: str, type_key: str, title: str, **extra
) -> dict:
    response = client.post(
        f"/api/v1/universes/{universe_id}/entities",
        json={"entity_type_key": type_key, "title": title, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_document(
    client: TestClient, universe_id: str, title: str, **extra
) -> dict:
    response = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={"title": title, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def patch_document(
    client: TestClient,
    universe_id: str,
    document_id: str,
    expected_version: int,
    **extra,
) -> dict:
    response = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{document_id}",
        json={"expected_version": expected_version, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def rich_content(entity_id: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Chronicle"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Bold",
                        "marks": [{"type": "bold"}],
                    },
                    {"type": "text", "text": " and "},
                    {
                        "type": "entityMention",
                        "attrs": {"entityId": entity_id, "label": "Aria"},
                    },
                    {"type": "text", "text": " and "},
                    {
                        "type": "wikiLink",
                        "attrs": {"label": "Northern Gate"},
                    },
                    {"type": "text", "text": " link"},
                    {
                        "type": "text",
                        "text": " (example)",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {"href": "https://example.com"},
                            }
                        ],
                    },
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "First"}],
                            }
                        ],
                    }
                ],
            },
            {
                "type": "blockquote",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Quoted"}],
                    }
                ],
            },
            {
                "type": "codeBlock",
                "attrs": {"language": "python"},
                "content": [{"type": "text", "text": "print('ok')"}],
            },
        ],
    }


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

def test_markdown_serializer_roundtrip_preserves_supported_vocabulary():
    entity_id = str(uuid.uuid4())
    content = rich_content(entity_id)
    markdown = tiptap_to_markdown(content)
    assert "# Chronicle" in markdown
    assert "**Bold**" in markdown
    assert f"[[Aria|ww:{entity_id}]]" in markdown
    assert "[[Northern Gate]]" in markdown
    assert "[ (example)](https://example.com)" in markdown
    assert "- First" in markdown
    assert "> Quoted" in markdown
    assert "```python" in markdown

    parsed = markdown_to_tiptap(markdown)
    assert parsed["type"] == "doc"
    assert parsed["content"][0]["type"] == "heading"
    mention = next(
        node
        for block in parsed["content"]
        if block.get("type") == "paragraph"
        for node in block.get("content", [])
        if node.get("type") == "entityMention"
    )
    assert mention["attrs"]["entityId"] == entity_id
    assert mention["attrs"]["label"] == "Aria"


def test_document_content_and_mentions_validate_against_tenant(open_client: TestClient):
    client = open_client
    register_user(client, "content_owner@example.com", "Owner")
    universe_a = create_universe(client, "Content A")
    universe_b = create_universe(client, "Content B")
    aria = create_entity(client, universe_a, "character", "Aria")
    foreign = create_entity(client, universe_b, "character", "Foreign")

    created = client.post(
        f"/api/v1/universes/{universe_a}/documents",
        json={
            "title": "The First Chapter",
            "document_type": "chapter",
            "content_json": rich_content(aria["id"]),
        },
    )
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["version"] == 1
    assert document["current_revision_number"] == 1
    assert document["revision_count"] == 1
    assert [link["entity_id"] for link in document["entity_links"]] == [aria["id"]]
    assert document["permissions"]["can_edit"] is True

    snapshot = client.get(
        f"/api/v1/universes/{universe_a}/documents/{document['id']}/revisions",
        params={"include_content": True},
    )
    assert snapshot.status_code == 200
    assert f"[[Aria|ww:{aria['id']}]]" in snapshot.json()["items"][0]["markdown_snapshot"]
    assert snapshot.json()["items"][0]["source"] == "manual"

    bad_node = client.post(
        f"/api/v1/universes/{universe_a}/documents",
        json={
            "title": "Script Injection",
            "content_json": {
                "type": "doc",
                "content": [{"type": "script", "content": []}],
            },
        },
    )
    assert bad_node.status_code == 422
    assert bad_node.json()["error"]["details"]["fields"][0]["code"] == "unsupported_node"

    unsafe_link = client.post(
        f"/api/v1/universes/{universe_a}/documents",
        json={
            "title": "Unsafe Link",
            "content_json": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "click",
                                "marks": [
                                    {
                                        "type": "link",
                                        "attrs": {"href": "javascript:alert(1)"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        },
    )
    assert unsafe_link.status_code == 422
    assert unsafe_link.json()["error"]["details"]["fields"][0]["code"] == "unsafe_link"

    cross_universe = client.post(
        f"/api/v1/universes/{universe_a}/documents",
        json={
            "title": "Foreign Mention",
            "content_json": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "entityMention",
                                "attrs": {
                                    "entityId": foreign["id"],
                                    "label": "Foreign",
                                },
                            }
                        ],
                    }
                ],
            },
        },
    )
    assert cross_universe.status_code == 422
    assert (
        cross_universe.json()["error"]["details"]["fields"][0]["code"]
        == "entity_not_found"
    )


def test_hierarchy_slugs_tree_and_parent_constraints(open_client: TestClient):
    client = open_client
    register_user(client, "hierarchy_owner@example.com", "Owner")
    universe_id = create_universe(client, "Hierarchy Realm")

    collection = create_document(
        client, universe_id, "Saga", document_type="collection"
    )
    work = create_document(
        client,
        universe_id,
        "First Age",
        document_type="work",
        parent_id=collection["id"],
    )
    part = create_document(
        client, universe_id, "Book One", document_type="part", parent_id=work["id"]
    )
    chapter = create_document(
        client, universe_id, "Arrival", document_type="chapter", parent_id=part["id"]
    )
    scene = create_document(
        client, universe_id, "The Gate", document_type="scene", parent_id=chapter["id"]
    )

    invalid_parent = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={
            "title": "Wrong Nesting",
            "document_type": "scene",
            "parent_id": work["id"],
        },
    )
    assert invalid_parent.status_code == 422
    assert (
        invalid_parent.json()["error"]["details"]["fields"][0]["code"]
        == "invalid_parent_type"
    )

    collection_with_parent = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={
            "title": "Nested Collection",
            "document_type": "collection",
            "parent_id": collection["id"],
        },
    )
    assert collection_with_parent.status_code == 422

    duplicate_slug = create_document(client, universe_id, "Saga")
    assert duplicate_slug["slug"] == "saga-2"

    tree = client.get(f"/api/v1/universes/{universe_id}/documents/tree")
    assert tree.status_code == 200
    roots = tree.json()["items"]
    root = next(item for item in roots if item["id"] == collection["id"])
    assert root["children"][0]["id"] == work["id"]
    assert root["children"][0]["children"][0]["id"] == part["id"]

    listed = client.get(
        f"/api/v1/universes/{universe_id}/documents",
        params={"parent_id": chapter["id"]},
    )
    assert [item["id"] for item in listed.json()["items"]] == [scene["id"]]

    bad_cycle = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{chapter['id']}",
        json={"expected_version": chapter["version"], "parent_id": scene["id"]},
    )
    assert bad_cycle.status_code == 422
    assert (
        bad_cycle.json()["error"]["details"]["fields"][0]["code"]
        == "invalid_parent_type"
    )


def test_optimistic_concurrency_revisions_and_restore(open_client: TestClient):
    client = open_client
    register_user(client, "revision_owner@example.com", "Owner")
    universe_id = create_universe(client, "Revision Realm")
    document = create_document(client, universe_id, "Draft")
    first_content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Original"}],
            }
        ],
    }
    second_content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Revised"}],
            }
        ],
    }

    updated = patch_document(
        client,
        universe_id,
        document["id"],
        document["version"],
        content_json=first_content,
        change_summary="First draft",
    )
    assert updated["version"] == 2
    assert updated["current_revision_number"] == 2

    stale = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}",
        json={"expected_version": document["version"], "title": "Stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert stale.json()["error"]["details"]["current_version"] == 2

    revised = patch_document(
        client,
        universe_id,
        document["id"],
        updated["version"],
        content_json=second_content,
    )
    assert revised["version"] == 3

    revisions = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}/revisions",
        params={"include_content": True, "limit": 10},
    )
    assert revisions.status_code == 200
    payload = revisions.json()
    assert payload["total"] == 3
    by_number = {item["revision_number"]: item for item in payload["items"]}
    assert by_number[1]["change_summary"] == "Initial version"
    assert by_number[2]["change_summary"] == "First draft"
    assert by_number[1]["content_json"] == {"type": "doc", "content": []}

    restored = client.post(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}/restore/{by_number[1]['id']}",
        json={"expected_version": revised["version"]},
    )
    assert restored.status_code == 200, restored.text
    restored_document = restored.json()
    assert restored_document["content_json"] == {"type": "doc", "content": []}
    assert restored_document["version"] == 4
    assert restored_document["current_revision_number"] == 5

    history = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}/revisions",
        params={"include_content": True},
    ).json()
    assert history["total"] == 5
    sources = {item["revision_number"]: item["source"] for item in history["items"]}
    assert sources[3] == "manual"
    assert sources[4] == "checkpoint"
    assert sources[5] == "restore"

    duplicate_restore = client.post(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}/restore/{by_number[1]['id']}",
        json={"expected_version": restored_document["version"]},
    )
    assert duplicate_restore.status_code == 200
    assert duplicate_restore.json()["version"] == 5
    assert duplicate_restore.json()["current_revision_number"] == 6


def test_visibility_scopes_for_drafts_restricted_and_private(open_client: TestClient):
    client = open_client
    register_user(client, "visibility_owner@example.com", "Owner")
    universe_id = create_universe(client, "Visibility Realm")
    add_member(
        client,
        universe_id,
        "visibility_owner@example.com",
        "editor_visibility@example.com",
        "editor",
    )
    add_member(
        client,
        universe_id,
        "visibility_owner@example.com",
        "contributor_visibility@example.com",
        "contributor",
    )
    add_member(
        client,
        universe_id,
        "visibility_owner@example.com",
        "viewer_visibility@example.com",
        "viewer",
    )

    login(client, "visibility_owner@example.com")
    public = create_document(client, universe_id, "Public Lore")
    restricted = create_document(
        client, universe_id, "Restricted Lore", visibility="restricted"
    )
    draft = create_document(client, universe_id, "Draft Lore", visibility="draft")
    draft_parent = create_document(
        client,
        universe_id,
        "Draft Saga",
        document_type="work",
        visibility="draft",
    )
    private = create_document(client, universe_id, "Private Lore", visibility="private")

    login(client, "viewer_visibility@example.com")
    visible = client.get(f"/api/v1/universes/{universe_id}/documents").json()
    assert {item["id"] for item in visible["items"]} == {public["id"]}
    for hidden in (restricted, draft, draft_parent, private):
        assert (
            client.get(
                f"/api/v1/universes/{universe_id}/documents/{hidden['id']}"
            ).status_code
            == 404
        )

    login(client, "contributor_visibility@example.com")
    contributor_visible = client.get(
        f"/api/v1/universes/{universe_id}/documents"
    ).json()
    assert {item["id"] for item in contributor_visible["items"]} == {public["id"]}

    login(client, "editor_visibility@example.com")
    editor_visible = client.get(f"/api/v1/universes/{universe_id}/documents").json()
    assert {item["id"] for item in editor_visible["items"]} == {
        public["id"],
        restricted["id"],
        draft["id"],
        draft_parent["id"],
    }

    login(client, "visibility_owner@example.com")
    owner_visible = client.get(f"/api/v1/universes/{universe_id}/documents").json()
    assert {item["id"] for item in owner_visible["items"]} == {
        public["id"],
        restricted["id"],
        draft["id"],
        draft_parent["id"],
        private["id"],
    }

    too_broad = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={
            "title": "Leaky Child",
            "document_type": "chapter",
            "parent_id": draft_parent["id"],
            "visibility": "universe",
        },
    )
    assert too_broad.status_code == 422
    assert (
        too_broad.json()["error"]["details"]["fields"][0]["code"]
        == "visibility_too_broad"
    )


def test_contributor_draft_workflow_and_comments(open_client: TestClient):
    client = open_client
    register_user(client, "workflow_owner@example.com", "Owner")
    universe_id = create_universe(client, "Workflow Realm")
    add_member(
        client,
        universe_id,
        "workflow_owner@example.com",
        "workflow_editor@example.com",
        "editor",
    )
    add_member(
        client,
        universe_id,
        "workflow_owner@example.com",
        "workflow_contributor@example.com",
        "contributor",
    )
    add_member(
        client,
        universe_id,
        "workflow_owner@example.com",
        "workflow_viewer@example.com",
        "viewer",
    )

    login(client, "workflow_owner@example.com")
    shared = create_document(client, universe_id, "Shared Chapter")

    login(client, "workflow_contributor@example.com")
    created = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={"title": "Contributor Draft", "document_type": "chapter"},
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["visibility"] == "draft"
    assert draft["status"] == "draft"

    forbidden_publish = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{draft['id']}",
        json={"expected_version": draft["version"], "status": "published"},
    )
    assert forbidden_publish.status_code == 403

    submitted = patch_document(
        client, universe_id, draft["id"], draft["version"], status="review"
    )
    assert submitted["status"] == "review"
    locked = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{draft['id']}",
        json={"expected_version": submitted["version"], "title": "Locked"},
    )
    assert locked.status_code == 403

    comment = client.post(
        f"/api/v1/universes/{universe_id}/documents/{shared['id']}/comments",
        json={"body": "  A useful note.  "},
    )
    assert comment.status_code == 201, comment.text
    assert comment.json()["body"] == "A useful note."

    reply = client.post(
        f"/api/v1/universes/{universe_id}/documents/{shared['id']}/comments",
        json={"body": "Reply", "parent_comment_id": comment.json()["id"]},
    )
    assert reply.status_code == 201
    nested = client.post(
        f"/api/v1/universes/{universe_id}/documents/{shared['id']}/comments",
        json={"body": "Nested", "parent_comment_id": reply.json()["id"]},
    )
    assert nested.status_code == 422

    edited = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{shared['id']}/comments/{comment.json()['id']}",
        json={"body": "Edited note."},
    )
    assert edited.status_code == 200
    assert edited.json()["body"] == "Edited note."
    assert edited.json()["edited_at"] is not None

    login(client, "workflow_viewer@example.com")
    viewer_comment = client.post(
        f"/api/v1/universes/{universe_id}/documents/{shared['id']}/comments",
        json={"body": "Should fail"},
    )
    assert viewer_comment.status_code == 403
    comments = client.get(
        f"/api/v1/universes/{universe_id}/documents/{shared['id']}/comments"
    )
    assert comments.status_code == 200
    assert comments.json()["total"] == 2

    login(client, "workflow_contributor@example.com")
    deleted = client.delete(
        f"/api/v1/universes/{universe_id}/documents/{shared['id']}/comments/{comment.json()['id']}"
    )
    assert deleted.status_code == 204
    remaining = client.get(
        f"/api/v1/universes/{universe_id}/documents/{shared['id']}/comments"
    ).json()
    assert remaining["total"] == 0

    login(client, "workflow_editor@example.com")
    published = patch_document(
        client,
        universe_id,
        draft["id"],
        submitted["version"],
        status="published",
        visibility="universe",
    )
    assert published["status"] == "published"
    assert published["visibility"] == "universe"


def test_entity_links_backlinks_and_visibility_filtering(open_client: TestClient):
    client = open_client
    register_user(client, "links_owner@example.com", "Owner")
    universe_id = create_universe(client, "Links Realm")
    add_member(
        client,
        universe_id,
        "links_owner@example.com",
        "links_editor@example.com",
        "editor",
    )
    add_member(
        client,
        universe_id,
        "links_owner@example.com",
        "links_contributor@example.com",
        "contributor",
    )

    login(client, "links_editor@example.com")
    public_entity = create_entity(client, universe_id, "character", "Public Hero")
    private_entity = create_entity(
        client, universe_id, "character", "Secret Hero", visibility="private"
    )
    content = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "entityMention",
                        "attrs": {
                            "entityId": public_entity["id"],
                            "label": "Public Hero",
                        },
                    },
                    {"type": "text", "text": " and "},
                    {
                        "type": "entityMention",
                        "attrs": {
                            "entityId": private_entity["id"],
                            "label": "Secret Hero",
                        },
                    },
                ],
            }
        ],
    }
    document = create_document(
        client, universe_id, "Linked Lore", content_json=content
    )
    assert {link["entity_id"] for link in document["entity_links"]} == {
        public_entity["id"],
        private_entity["id"],
    }

    backlinks = client.get(
        f"/api/v1/universes/{universe_id}/entities/{public_entity['id']}/documents"
    )
    assert backlinks.status_code == 200
    assert [item["id"] for item in backlinks.json()["items"]] == [document["id"]]

    login(client, "links_contributor@example.com")
    contributor_links = client.get(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}/links"
    )
    assert contributor_links.status_code == 200
    assert [link["entity_id"] for link in contributor_links.json()] == [
        public_entity["id"]
    ]
    assert (
        client.get(
            f"/api/v1/universes/{universe_id}/entities/{private_entity['id']}/documents"
        ).status_code
        == 404
    )


def test_document_delete_restore_cascade_and_tenant_isolation(open_client: TestClient):
    client = open_client
    register_user(client, "delete_owner@example.com", "Owner")
    universe_a = create_universe(client, "Delete Realm")
    universe_b = create_universe(client, "Other Realm")

    parent = create_document(
        client, universe_a, "Saga", document_type="collection"
    )
    child = create_document(
        client,
        universe_a,
        "Book",
        document_type="work",
        parent_id=parent["id"],
    )

    cross_universe_parent = client.post(
        f"/api/v1/universes/{universe_b}/documents",
        json={
            "title": "Wrong Tenant",
            "document_type": "work",
            "parent_id": parent["id"],
        },
    )
    assert cross_universe_parent.status_code == 404
    assert cross_universe_parent.json()["error"]["code"] == "document_not_found"

    assert (
        client.get(
            f"/api/v1/universes/{universe_b}/documents/{parent['id']}"
        ).status_code
        == 404
    )

    removed = client.delete(
        f"/api/v1/universes/{universe_a}/documents/{parent['id']}"
    )
    assert removed.status_code == 204
    assert (
        client.get(
            f"/api/v1/universes/{universe_a}/documents/{parent['id']}"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/universes/{universe_a}/documents/{child['id']}"
        ).status_code
        == 404
    )

    restore_child_first = client.post(
        f"/api/v1/universes/{universe_a}/documents/{child['id']}/restore"
    )
    assert restore_child_first.status_code == 409
    assert restore_child_first.json()["error"]["code"] == "parent_deleted"

    restored_parent = client.post(
        f"/api/v1/universes/{universe_a}/documents/{parent['id']}/restore"
    )
    assert restored_parent.status_code == 200
    restored_child = client.post(
        f"/api/v1/universes/{universe_a}/documents/{child['id']}/restore"
    )
    assert restored_child.status_code == 200
    assert restored_child.json()["parent_id"] == parent["id"]


def test_private_document_is_hidden_from_other_editors(open_client: TestClient):
    client = open_client
    register_user(client, "private_owner@example.com", "Owner")
    universe_id = create_universe(client, "Private Realm")
    add_member(
        client,
        universe_id,
        "private_owner@example.com",
        "editor_one@example.com",
        "editor",
    )
    add_member(
        client,
        universe_id,
        "private_owner@example.com",
        "editor_two@example.com",
        "editor",
    )

    login(client, "editor_one@example.com")
    private = create_document(
        client, universe_id, "Editor One Notes", visibility="private"
    )

    login(client, "editor_two@example.com")
    assert (
        client.get(
            f"/api/v1/universes/{universe_id}/documents/{private['id']}"
        ).status_code
        == 404
    )
    listed = client.get(f"/api/v1/universes/{universe_id}/documents").json()
    assert private["id"] not in {item["id"] for item in listed["items"]}

    login(client, "private_owner@example.com")
    assert (
        client.get(
            f"/api/v1/universes/{universe_id}/documents/{private['id']}"
        ).status_code
        == 200
    )


def test_archived_universe_blocks_chronicle_mutations(open_client: TestClient):
    client = open_client
    register_user(client, "chronicle_archive@example.com", "Owner")
    universe_id = create_universe(client, "Chronicle Archive Realm")
    document = create_document(client, universe_id, "Before Archive")
    assert (
        client.post(f"/api/v1/universes/{universe_id}/archive").status_code == 200
    )

    blocked_create = client.post(
        f"/api/v1/universes/{universe_id}/documents",
        json={"title": "After Archive"},
    )
    assert blocked_create.status_code == 409
    assert blocked_create.json()["error"]["code"] == "universe_archived"

    blocked_update = client.patch(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}",
        json={"expected_version": document["version"], "title": "Changed"},
    )
    assert blocked_update.status_code == 409
    assert blocked_update.json()["error"]["code"] == "universe_archived"

    blocked_comment = client.post(
        f"/api/v1/universes/{universe_id}/documents/{document['id']}/comments",
        json={"body": "Nope"},
    )
    assert blocked_comment.status_code == 409

    assert (
        client.get(
            f"/api/v1/universes/{universe_id}/documents/{document['id']}"
        ).status_code
        == 200
    )
