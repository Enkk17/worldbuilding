from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from backend.core.errors import ApiError
from backend.core.models import (
    Comment,
    Document,
    DocumentCollabSnapshot,
    DocumentCollabUpdate,
    DocumentEntityLink,
    DocumentRevision,
    Entity,
    EntityType,
    Universe,
    User,
)
from backend.core.permissions import Action, Role, has_permission
from backend.core.security import state_hash
from backend.core.visibility import is_visible, visible_clause
from backend.modules.chronicle.content import (
    ContentValidationError,
    content_preview,
    empty_document,
    extract_mentions,
    normalize_document_content,
)
from backend.modules.chronicle.markdown import tiptap_to_markdown
from backend.modules.chronicle.schemas import (
    CommentCreate,
    CommentUpdate,
    DocumentCreate,
    DocumentRestoreRequest,
    DocumentUpdate,
)
from backend.modules.universes.service import (
    check_universe_access,
    record_activity,
    record_audit,
    slugify,
)

DOCUMENT_TYPES = frozenset(
    {"collection", "work", "part", "chapter", "scene", "note"}
)
DOCUMENT_STATUSES = frozenset({"draft", "review", "published", "archived"})
DOCUMENT_VISIBILITIES = frozenset({"universe", "restricted", "draft", "private"})
REVISION_SOURCES = frozenset(
    {"manual", "checkpoint", "publish", "restore", "import", "autosave"}
)

ALLOWED_PARENT_TYPES: dict[str, frozenset[str]] = {
    "collection": frozenset(),
    "work": frozenset({"collection"}),
    "part": frozenset({"collection", "work"}),
    "chapter": frozenset({"collection", "work", "part"}),
    "scene": frozenset({"chapter"}),
    "note": frozenset({"collection", "work", "part", "chapter", "scene"}),
}

VISIBILITY_RANK = {
    "universe": 0,
    "restricted": 1,
    "draft": 2,
    "private": 3,
}

MAX_TREE_DOCUMENTS = 5_000
MAX_COMMENT_ANCHOR_QUOTE = 1_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fail_validation(
    field: str, code: str, message: str, **extra: Any
) -> None:
    raise ApiError(
        422,
        "validation_error",
        message,
        details={"fields": [{"field": field, "code": code, **extra}]},
    )


def _validate_choice(
    value: str | None, allowed: frozenset[str], field: str
) -> None:
    if value is not None and value not in allowed:
        _fail_validation(
            field,
            "invalid_value",
            f"Unsupported value for '{field}'.",
            allowed=sorted(allowed),
        )


def _ensure_mutable(universe: Universe) -> None:
    if universe.status == "archived":
        raise ApiError(
            409,
            "universe_archived",
            "This universe is archived and read-only. Restore it before making changes.",
        )


def _normalise_content(value: Any) -> dict[str, Any]:
    try:
        return normalize_document_content(value)
    except ContentValidationError as exc:
        raise ApiError(
            422,
            "validation_error",
            "Document content is invalid.",
            details={
                "fields": [
                    {
                        "field": "content_json",
                        "code": exc.code,
                        "path": exc.path,
                        "message": exc.message,
                    }
                ]
            },
        ) from exc


def _normalise_body(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        _fail_validation("body", "body_required", "Comment bodies cannot be empty.")
    if len(cleaned) > 5_000:
        _fail_validation(
            "body", "body_too_long", "Comment bodies cannot exceed 5000 characters."
        )
    return cleaned


def _normalise_comment_anchor(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        _fail_validation("anchor_json", "invalid_anchor", "Anchors must be objects.")
    allowed = {"from", "to", "quote"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        _fail_validation(
            "anchor_json",
            "unknown_anchor_keys",
            "Comment anchors contain unsupported keys.",
            keys=unknown,
        )
    cleaned: dict[str, Any] = {}
    for key in ("from", "to"):
        if value.get(key) is None:
            continue
        position = value[key]
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position < 0
            or position > 10_000_000
        ):
            _fail_validation(
                f"anchor_json.{key}",
                "invalid_anchor_position",
                "Anchor positions must be non-negative integers.",
            )
        cleaned[key] = position
    if "from" in cleaned and "to" in cleaned and cleaned["from"] > cleaned["to"]:
        _fail_validation(
            "anchor_json",
            "invalid_anchor_range",
            "Anchor start must not be greater than its end.",
        )
    if value.get("quote") is not None:
        quote = value["quote"]
        if not isinstance(quote, str) or len(quote) > MAX_COMMENT_ANCHOR_QUOTE:
            _fail_validation(
                "anchor_json.quote",
                "invalid_anchor_quote",
                f"Anchor quotes cannot exceed {MAX_COMMENT_ANCHOR_QUOTE} characters.",
            )
        cleaned["quote"] = quote
    return cleaned or None


def _slug_base(value: str) -> str:
    base = slugify(value)[:200]
    if base == "universe" and value.strip().lower() != "universe":
        base = "document"
    return base


def _unique_document_slug(
    db: Session,
    universe_id: uuid.UUID,
    base_value: str,
    exclude_id: uuid.UUID | None = None,
) -> str:
    base = _slug_base(base_value)
    candidate = base
    counter = 2
    while True:
        stmt = select(Document.id).where(
            Document.universe_id == universe_id, Document.slug == candidate
        )
        if exclude_id is not None:
            stmt = stmt.where(Document.id != exclude_id)
        if db.scalar(stmt) is None:
            return candidate
        candidate = f"{base}-{counter}"[:200]
        counter += 1


def _get_document_raw(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.id == document_id, Document.universe_id == universe_id
        )
    )
    if document is None or (document.deleted_at is not None and not include_deleted):
        raise ApiError(404, "document_not_found", "Document not found.")
    return document


def _get_visible_document(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
    role: str,
    *,
    include_deleted: bool = False,
) -> Document:
    document = _get_document_raw(
        db, universe_id, document_id, include_deleted=include_deleted
    )
    if not is_visible(document, user.id, role):
        raise ApiError(404, "document_not_found", "Document not found.")
    return document


def _validate_parent(
    db: Session,
    universe_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    document_type: str,
    *,
    current_document_id: uuid.UUID | None = None,
) -> Document | None:
    if parent_id is None:
        return None
    parent = _get_document_raw(db, universe_id, parent_id)
    allowed = ALLOWED_PARENT_TYPES[document_type]
    if not allowed:
        _fail_validation(
            "parent_id",
            "parent_not_allowed",
            f"Documents of type '{document_type}' cannot have a parent.",
        )
    if parent.document_type not in allowed:
        _fail_validation(
            "parent_id",
            "invalid_parent_type",
            f"A {document_type} cannot be nested under a {parent.document_type}.",
            allowed_parent_types=sorted(allowed),
        )
    if current_document_id is not None:
        _assert_no_cycle(db, universe_id, current_document_id, parent_id)
    return parent


def _assert_no_cycle(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    parent_id: uuid.UUID,
) -> None:
    seen: set[uuid.UUID] = set()
    cursor: uuid.UUID | None = parent_id
    while cursor is not None:
        if cursor == document_id:
            raise ApiError(
                409,
                "document_cycle",
                "A document cannot be moved beneath itself or one of its descendants.",
            )
        if cursor in seen:
            raise ApiError(
                409,
                "document_cycle",
                "The document hierarchy contains a cycle and must be repaired.",
            )
        seen.add(cursor)
        ancestor = db.get(Document, cursor)
        if ancestor is None or ancestor.universe_id != universe_id:
            _fail_validation(
                "parent_id", "parent_not_found", "The requested parent does not exist."
            )
        cursor = ancestor.parent_id


def _validate_visibility_against_parent(
    visibility: str, parent: Document | None
) -> None:
    if parent is None:
        return
    if VISIBILITY_RANK[visibility] < VISIBILITY_RANK.get(parent.visibility, 0):
        _fail_validation(
            "visibility",
            "visibility_too_broad",
            "A document cannot be more visible than its parent.",
            parent_visibility=parent.visibility,
        )


def _validate_children_visibility(
    db: Session, document: Document, visibility: str
) -> None:
    child_visibilities = set(
        db.scalars(
            select(Document.visibility).where(
                Document.universe_id == document.universe_id,
                Document.parent_id == document.id,
                Document.deleted_at.is_(None),
            )
        ).all()
    )
    too_broad = sorted(
        child_visibility
        for child_visibility in child_visibilities
        if VISIBILITY_RANK.get(child_visibility, 0) < VISIBILITY_RANK[visibility]
    )
    if too_broad:
        _fail_validation(
            "visibility",
            "children_visibility_too_broad",
            "Child documents would become more visible than this document.",
            child_visibilities=too_broad,
        )


def _validate_children_types(
    db: Session, document: Document, document_type: str
) -> None:
    child_types = set(
        db.scalars(
            select(Document.document_type).where(
                Document.universe_id == document.universe_id,
                Document.parent_id == document.id,
                Document.deleted_at.is_(None),
            )
        ).all()
    )
    allowed = ALLOWED_PARENT_TYPES[document_type]
    invalid = sorted(child_type for child_type in child_types if child_type not in allowed)
    if invalid:
        _fail_validation(
            "document_type",
            "invalid_child_types",
            "Existing child documents are incompatible with the requested type.",
            child_types=invalid,
        )


def _validate_mentions(
    db: Session,
    universe_id: uuid.UUID,
    content: dict[str, Any],
    user: User,
    role: str,
    *,
    allow_deleted: bool = False,
    enforce_visibility: bool = True,
) -> list[Any]:
    mentions = extract_mentions(content)
    entity_ids = {mention.entity_id for mention in mentions}
    if not entity_ids:
        return mentions

    stmt = select(Entity.id).where(
        Entity.universe_id == universe_id, Entity.id.in_(entity_ids)
    )
    if not allow_deleted:
        stmt = stmt.where(Entity.deleted_at.is_(None))
    if enforce_visibility:
        clause = visible_clause(Entity, user.id, role)
        if clause is not None:
            stmt = stmt.where(clause)
    found = set(db.scalars(stmt).all())
    missing = entity_ids - found
    if missing:
        raise ApiError(
            422,
            "validation_error",
            "Document content references entities that are unavailable.",
            details={
                "fields": [
                    {
                        "field": "content_json",
                        "code": "entity_not_found",
                        "entity_ids": [str(value) for value in sorted(missing, key=str)][:25],
                    }
                ]
            },
        )
    return mentions


def _replace_entity_links(
    db: Session, document: Document, mentions: list[Any]
) -> None:
    db.execute(
        delete(DocumentEntityLink).where(
            DocumentEntityLink.document_id == document.id
        )
    )
    for mention in mentions:
        db.add(
            DocumentEntityLink(
                id=uuid.uuid4(),
                document_id=document.id,
                entity_id=mention.entity_id,
                anchor_json={"path": mention.path, "label": mention.label},
                link_kind="mention",
            )
        )


def _has_children_map(
    db: Session, universe_id: uuid.UUID, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not document_ids:
        return {}
    rows = db.execute(
        select(Document.parent_id, func.count(Document.id))
        .where(
            Document.universe_id == universe_id,
            Document.deleted_at.is_(None),
            Document.parent_id.in_(document_ids),
        )
        .group_by(Document.parent_id)
    ).all()
    return {parent_id: int(count) for parent_id, count in rows if parent_id is not None}


def _revision_stats(
    db: Session, document_id: uuid.UUID
) -> tuple[int, int]:
    row = db.execute(
        select(
            func.count(DocumentRevision.id),
            func.max(DocumentRevision.revision_number),
        ).where(DocumentRevision.document_id == document_id)
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


def can_edit_document(user: User, role: str, document: Document) -> bool:
    """Single source of truth for document write access.

    Editors and above may update documents. A contributor may only update
    their own document while it is still a draft; submitting for review locks
    the content until an editor acts on it.
    """

    return has_permission(role, Action.DOCUMENT_UPDATE) or (
        role == Role.CONTRIBUTOR.value
        and document.created_by == user.id
        and document.status == "draft"
    )


def _document_permissions(user: User, role: str, document: Document) -> dict[str, bool]:
    can_edit = can_edit_document(user, role, document)
    return {
        "can_edit": can_edit,
        "can_delete": has_permission(role, Action.DOCUMENT_DELETE),
        "can_restore": has_permission(role, Action.DOCUMENT_RESTORE),
        "can_comment": has_permission(role, Action.DOCUMENT_COMMENT),
        "can_review": has_permission(role, Action.DOCUMENT_REVIEW),
    }


def _document_state(document: Document) -> dict[str, Any]:
    content = document.content_json if isinstance(document.content_json, dict) else {}
    return {
        "title": document.title,
        "slug": document.slug,
        "document_type": document.document_type,
        "status": document.status,
        "visibility": document.visibility,
        "parent_id": str(document.parent_id) if document.parent_id else None,
        "sort_order": document.sort_order,
        "content_hash": state_hash(content),
    }


def _document_summary(document: Document, *, has_children: bool) -> dict[str, Any]:
    content = document.content_json if isinstance(document.content_json, dict) else empty_document()
    try:
        excerpt = content_preview(content)
    except (AttributeError, TypeError):
        excerpt = ""
    return {
        "id": document.id,
        "universe_id": document.universe_id,
        "parent_id": document.parent_id,
        "document_type": document.document_type,
        "title": document.title,
        "slug": document.slug,
        "status": document.status,
        "visibility": document.visibility,
        "sort_order": document.sort_order,
        "created_by": document.created_by,
        "updated_by": document.updated_by,
        "version": document.version,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "excerpt": excerpt,
        "has_children": has_children,
    }


def _breadcrumbs(
    db: Session, document: Document, user: User, role: str
) -> list[dict[str, Any]]:
    trail: list[Document] = []
    cursor = document.parent_id
    seen: set[uuid.UUID] = set()
    while cursor is not None and cursor not in seen and len(trail) < 100:
        seen.add(cursor)
        parent = db.get(Document, cursor)
        if (
            parent is None
            or parent.universe_id != document.universe_id
            or parent.deleted_at is not None
            or not is_visible(parent, user.id, role)
        ):
            break
        trail.append(parent)
        cursor = parent.parent_id
    trail.reverse()
    return [
        {
            "id": item.id,
            "title": item.title,
            "document_type": item.document_type,
        }
        for item in trail
    ]


def _document_entity_links(
    db: Session, document: Document, user: User, role: str
) -> list[dict[str, Any]]:
    stmt = (
        select(DocumentEntityLink, Entity, EntityType)
        .join(Entity, Entity.id == DocumentEntityLink.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(
            DocumentEntityLink.document_id == document.id,
            Entity.universe_id == document.universe_id,
        )
        .order_by(Entity.title.asc(), DocumentEntityLink.id.asc())
    )
    clause = visible_clause(Entity, user.id, role)
    if clause is not None:
        stmt = stmt.where(clause)
    grouped: dict[uuid.UUID, dict[str, Any]] = {}
    for link, entity, entity_type in db.execute(stmt).all():
        entry = grouped.get(entity.id)
        if entry is None:
            anchor = link.anchor_json if isinstance(link.anchor_json, dict) else {}
            entry = {
                "entity_id": entity.id,
                "title": entity.title,
                "slug": entity.slug,
                "entity_type_key": entity_type.key,
                "entity_type_name": entity_type.name,
                "label": str(anchor.get("label") or entity.title),
                "link_kind": link.link_kind,
                "mention_count": 0,
                "entity_deleted": entity.deleted_at is not None,
            }
            grouped[entity.id] = entry
        entry["mention_count"] += 1
    return list(grouped.values())


def _document_detail(
    db: Session, document: Document, user: User, role: str
) -> dict[str, Any]:
    revision_count, current_revision = _revision_stats(db, document.id)
    has_children = bool(
        _has_children_map(db, document.universe_id, [document.id]).get(document.id)
    )
    data = _document_summary(document, has_children=has_children)
    data.update(
        {
            "content_json": document.content_json
            if isinstance(document.content_json, dict)
            else empty_document(),
            "current_revision_number": current_revision,
            "revision_count": revision_count,
            "breadcrumbs": _breadcrumbs(db, document, user, role),
            "entity_links": _document_entity_links(db, document, user, role),
            "permissions": _document_permissions(user, role, document),
        }
    )
    return data


def _revision_payload(
    revision: DocumentRevision, *, include_content: bool
) -> dict[str, Any]:
    return {
        "id": revision.id,
        "document_id": revision.document_id,
        "revision_number": revision.revision_number,
        "content_json": revision.content_json if include_content else None,
        "markdown_snapshot": revision.markdown_snapshot if include_content else None,
        "change_summary": revision.change_summary,
        "source": revision.source,
        "created_by": revision.created_by,
        "created_at": revision.created_at,
    }


def _next_revision_number(db: Session, document_id: uuid.UUID) -> int:
    current = db.scalar(
        select(func.max(DocumentRevision.revision_number)).where(
            DocumentRevision.document_id == document_id
        )
    )
    return int(current or 0) + 1


def _version_conflict(
    expected_version: int, document: Document
) -> None:
    raise ApiError(
        409,
        "version_conflict",
        (
            f"Version conflict: expected version {expected_version}, "
            f"but the document has version {document.version}."
        ),
        details={
            "current_version": document.version,
            "expected_version": expected_version,
            "updated_by": str(document.updated_by),
            "updated_at": document.updated_at.isoformat()
            if document.updated_at
            else None,
        },
    )


def collaboration_state_exists(db: Session, document_id: uuid.UUID) -> bool:
    snapshot = db.scalar(
        select(DocumentCollabSnapshot.id)
        .where(DocumentCollabSnapshot.document_id == document_id)
        .limit(1)
    )
    if snapshot is not None:
        return True
    update_row = db.scalar(
        select(DocumentCollabUpdate.id)
        .where(DocumentCollabUpdate.document_id == document_id)
        .limit(1)
    )
    return update_row is not None


def reset_collaboration_state(
    db: Session, universe_id: uuid.UUID, document_id: uuid.UUID
) -> int | None:
    """Invalidate every Yjs snapshot/update for a document.

    Used after revision restore (which replaces document content) and when a
    client has produced content outside the accepted schema. The generation
    counter makes live rooms detect the reset and disconnect instead of
    continuing to edit an obsolete CRDT state.
    """

    document = db.scalar(
        select(Document).where(
            Document.id == document_id, Document.universe_id == universe_id
        )
    )
    if document is None:
        return None
    document.collab_generation += 1
    db.execute(
        delete(DocumentCollabUpdate).where(
            DocumentCollabUpdate.document_id == document_id,
            DocumentCollabUpdate.universe_id == universe_id,
        )
    )
    db.execute(
        delete(DocumentCollabSnapshot).where(
            DocumentCollabSnapshot.document_id == document_id,
            DocumentCollabSnapshot.universe_id == universe_id,
        )
    )
    return document.collab_generation


def apply_collaborative_content(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_id: uuid.UUID,
    role: str,
    content_json: dict[str, Any],
    *,
    expected_generation: int,
    create_revision: bool = False,
    change_summary: str | None = None,
) -> dict[str, Any] | None:
    """Persist materialised TipTap JSON produced by a collaboration room.

    Collaboration does not use the REST optimistic-concurrency version for
    content: the CRDT stream is the write path and the materialised JSON is a
    projection. Metadata edits still use ``version``. The generation guard
    prevents a stale room from overwriting a revision restore.
    """

    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.universe_id == universe_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        return None
    if document.collab_generation != expected_generation:
        return None
    user = db.get(User, actor_id)
    if user is None:
        return None

    normalised = _normalise_content(content_json)
    # Mentions may point at an entity that was deleted or hidden after the
    # text was written. The content remains valid; the backlink read path
    # filters/decorates unavailable entities. Rejecting the projection would
    # otherwise discard legitimate collaborative edits.
    mentions = _validate_mentions(
        db,
        universe_id,
        normalised,
        user,
        role,
        allow_deleted=True,
        enforce_visibility=False,
    )
    current = (
        document.content_json
        if isinstance(document.content_json, dict)
        else empty_document()
    )
    changed = state_hash(current) != state_hash(normalised)
    now = _now()

    if changed:
        result = db.execute(
            update(Document)
            .where(
                Document.id == document.id,
                Document.universe_id == universe_id,
                Document.collab_generation == expected_generation,
                Document.deleted_at.is_(None),
            )
            .values(
                content_json=normalised,
                updated_by=actor_id,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            db.rollback()
            return None
        _replace_entity_links(db, document, mentions)

    revision_number: int | None = None
    if changed and create_revision:
        latest_content = db.scalar(
            select(DocumentRevision.content_json)
            .where(DocumentRevision.document_id == document.id)
            .order_by(DocumentRevision.revision_number.desc())
            .limit(1)
        )
        if latest_content is None or state_hash(latest_content) != state_hash(
            normalised
        ):
            revision_number = _next_revision_number(db, document.id)
            db.add(
                DocumentRevision(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    revision_number=revision_number,
                    content_json=normalised,
                    markdown_snapshot=tiptap_to_markdown(normalised),
                    change_summary=change_summary
                    or "Collaboration checkpoint",
                    source="autosave",
                    created_by=actor_id,
                    created_at=now,
                )
            )

    db.commit()
    return {
        "changed": changed,
        "revision_number": revision_number,
        "content": normalised,
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# -----------------------------------------------------------------------------
# Document reads
# -----------------------------------------------------------------------------

def list_documents(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    *,
    parent_id: uuid.UUID | None = None,
    root_only: bool = False,
    document_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    _, membership = check_universe_access(db, universe_id, user, Action.DOCUMENT_READ)
    _validate_choice(document_type, DOCUMENT_TYPES, "document_type")
    _validate_choice(status, DOCUMENT_STATUSES, "status")
    if parent_id is not None and root_only:
        _fail_validation(
            "parent_id",
            "conflicting_filters",
            "parent_id and root_only cannot be combined.",
        )
    if parent_id is not None:
        _get_visible_document(db, universe_id, parent_id, user, membership.role)

    predicates = [
        Document.universe_id == universe_id,
        Document.deleted_at.is_(None),
    ]
    visibility = visible_clause(Document, user.id, membership.role)
    if visibility is not None:
        predicates.append(visibility)
    if parent_id is not None:
        predicates.append(Document.parent_id == parent_id)
    elif root_only:
        predicates.append(Document.parent_id.is_(None))
    if document_type is not None:
        predicates.append(Document.document_type == document_type)
    if status is not None:
        predicates.append(Document.status == status)
    if search is not None:
        term = search.strip()
        if len(term) > 200:
            _fail_validation(
                "q", "search_too_long", "Search terms cannot exceed 200 characters."
            )
        if term:
            pattern = f"%{_escape_like(term)}%"
            predicates.append(
                or_(
                    Document.title.ilike(pattern, escape="\\"),
                    Document.slug.ilike(pattern, escape="\\"),
                )
            )

    total = int(
        db.scalar(select(func.count(Document.id)).where(*predicates)) or 0
    )
    sort_column = {
        "title": Document.title,
        "created_at": Document.created_at,
        "updated_at": Document.updated_at,
        "sort_order": Document.sort_order,
    }.get(sort)
    if sort_column is None:
        _fail_validation(
            "sort",
            "invalid_sort",
            "Unsupported sort field.",
            allowed=sorted(["title", "created_at", "updated_at", "sort_order"]),
        )
    if order not in {"asc", "desc"}:
        _fail_validation(
            "order", "invalid_order", "Order must be 'asc' or 'desc'."
        )
    order_clause = sort_column.asc() if order == "asc" else sort_column.desc()
    statement = (
        select(Document)
        .where(*predicates)
        .order_by(order_clause, Document.id.asc())
        .limit(min(limit, 500))
        .offset(max(offset, 0))
    )
    documents = list(db.scalars(statement).all())
    children = _has_children_map(
        db, universe_id, [document.id for document in documents]
    )
    return (
        [
            _document_summary(
                document, has_children=bool(children.get(document.id))
            )
            for document in documents
        ],
        total,
    )


def get_document_tree(
    db: Session, universe_id: uuid.UUID, user: User
) -> tuple[list[dict[str, Any]], int]:
    _, membership = check_universe_access(db, universe_id, user, Action.DOCUMENT_READ)
    predicates = [
        Document.universe_id == universe_id,
        Document.deleted_at.is_(None),
    ]
    visibility = visible_clause(Document, user.id, membership.role)
    if visibility is not None:
        predicates.append(visibility)
    total = int(
        db.scalar(select(func.count(Document.id)).where(*predicates)) or 0
    )
    if total > MAX_TREE_DOCUMENTS:
        raise ApiError(
            413,
            "document_tree_too_large",
            "The document tree exceeds the maximum supported size. Use the flat document listing with pagination.",
            details={"total": total, "limit": MAX_TREE_DOCUMENTS},
        )
    documents = list(
        db.scalars(
            select(Document)
            .where(*predicates)
            .order_by(
                Document.sort_order.asc(),
                Document.title.asc(),
                Document.id.asc(),
            )
        ).all()
    )
    nodes: dict[uuid.UUID, dict[str, Any]] = {}
    for document in documents:
        node = _document_summary(document, has_children=False)
        node["children"] = []
        nodes[document.id] = node
    roots: list[dict[str, Any]] = []
    for document in documents:
        node = nodes[document.id]
        parent = nodes.get(document.parent_id) if document.parent_id else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
    for node in nodes.values():
        node["has_children"] = bool(node["children"])
    return roots, total


def get_document_details(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
) -> dict[str, Any]:
    _, membership = check_universe_access(db, universe_id, user, Action.DOCUMENT_READ)
    document = _get_visible_document(
        db, universe_id, document_id, user, membership.role
    )
    return _document_detail(db, document, user, membership.role)


# -----------------------------------------------------------------------------
# Document writes
# -----------------------------------------------------------------------------

def create_document(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    data: DocumentCreate,
    request_id: str | None = None,
) -> dict[str, Any]:
    _, membership = check_universe_access(db, universe_id, user, Action.DOCUMENT_CREATE)
    role = membership.role
    _validate_choice(data.document_type, DOCUMENT_TYPES, "document_type")
    _validate_choice(data.status, DOCUMENT_STATUSES, "status")
    _validate_choice(data.visibility, DOCUMENT_VISIBILITIES, "visibility")

    visibility = data.visibility
    if role == Role.CONTRIBUTOR.value:
        if "visibility" not in data.model_fields_set:
            visibility = "draft"
        if data.status != "draft":
            raise ApiError(
                403,
                "permission_denied",
                "Contributors may only create draft documents.",
            )
        if visibility not in {"draft", "private"}:
            _fail_validation(
                "visibility",
                "visibility_not_allowed",
                "Contributors may create draft or private documents only.",
            )

    parent = _validate_parent(db, universe_id, data.parent_id, data.document_type)
    _validate_visibility_against_parent(visibility, parent)
    content = _normalise_content(data.content_json)
    mentions = _validate_mentions(db, universe_id, content, user, role)

    title = data.title.strip()
    if not title:
        _fail_validation("title", "title_required", "Document titles cannot be empty.")
    slug = _unique_document_slug(db, universe_id, data.slug or title)
    now = _now()
    document = Document(
        id=uuid.uuid4(),
        universe_id=universe_id,
        parent_id=parent.id if parent else None,
        document_type=data.document_type,
        title=title,
        slug=slug,
        content_json=content,
        status=data.status,
        visibility=visibility,
        sort_order=data.sort_order,
        created_by=user.id,
        updated_by=user.id,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(document)
    db.flush()

    _replace_entity_links(db, document, mentions)
    db.add(
        DocumentRevision(
            id=uuid.uuid4(),
            document_id=document.id,
            revision_number=1,
            content_json=content,
            markdown_snapshot=tiptap_to_markdown(content),
            change_summary=data.change_summary or "Initial version",
            source="publish" if data.status == "published" else "manual",
            created_by=user.id,
            created_at=now,
        )
    )
    record_audit(
        db,
        universe_id,
        user.id,
        "document.create",
        "document",
        document.id,
        after_hash=state_hash(_document_state(document)),
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "document.created",
        "document",
        document.id,
        {
            "title": document.title,
            "document_type": document.document_type,
            "status": document.status,
        },
    )
    db.commit()
    return _document_detail(db, document, user, role)


def update_document(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
    data: DocumentUpdate,
    request_id: str | None = None,
) -> dict[str, Any]:
    universe, membership = check_universe_access(
        db, universe_id, user, Action.DOCUMENT_READ
    )
    _ensure_mutable(universe)
    document = _get_visible_document(
        db, universe_id, document_id, user, membership.role
    )
    role = membership.role
    if not has_permission(role, Action.DOCUMENT_UPDATE):
        if not (
            role == Role.CONTRIBUTOR.value
            and document.created_by == user.id
            and document.status == "draft"
        ):
            raise ApiError(
                403,
                "permission_denied",
                "You do not have permission to edit this document.",
            )

    if document.version != data.expected_version:
        _version_conflict(data.expected_version, document)

    fields_set = data.model_fields_set
    new_title = data.title.strip() if data.title is not None else document.title
    if not new_title:
        _fail_validation("title", "title_required", "Document titles cannot be empty.")
    new_type = data.document_type or document.document_type
    new_parent_id = (
        data.parent_id if "parent_id" in fields_set else document.parent_id
    )
    new_status = data.status or document.status
    new_visibility = data.visibility or document.visibility
    new_sort_order = (
        data.sort_order if data.sort_order is not None else document.sort_order
    )
    content_changed = "content_json" in fields_set
    if content_changed and collaboration_state_exists(db, document.id):
        raise ApiError(
            409,
            "collaboration_content_conflict",
            (
                "This document has a realtime collaboration history. "
                "Content must be edited through the collaboration room."
            ),
            details={
                "current_version": document.version,
                "collab_generation": document.collab_generation,
            },
        )
    new_content = (
        _normalise_content(data.content_json)
        if content_changed
        else document.content_json
    )
    _validate_choice(new_type, DOCUMENT_TYPES, "document_type")
    _validate_choice(new_status, DOCUMENT_STATUSES, "status")
    _validate_choice(new_visibility, DOCUMENT_VISIBILITIES, "visibility")

    if role == Role.CONTRIBUTOR.value:
        if document.created_by != user.id or document.status != "draft":
            raise ApiError(
                403,
                "permission_denied",
                "Contributors may edit their own draft documents only.",
            )
        if new_status not in {"draft", "review"}:
            raise ApiError(
                403,
                "permission_denied",
                "Contributors cannot publish or archive documents.",
            )
        if new_visibility not in {"draft", "private"}:
            _fail_validation(
                "visibility",
                "visibility_not_allowed",
                "Contributors may keep documents draft or private only.",
            )

    new_parent = _validate_parent(
        db,
        universe_id,
        new_parent_id,
        new_type,
        current_document_id=document.id,
    )
    if new_type != document.document_type:
        _validate_children_types(db, document, new_type)
    if new_visibility != document.visibility:
        _validate_children_visibility(db, document, new_visibility)
    _validate_visibility_against_parent(new_visibility, new_parent)

    mentions: list[Any] = []
    if content_changed:
        mentions = _validate_mentions(
            db, universe_id, new_content, user, role
        )

    old_status = document.status
    before_state = _document_state(document)
    new_slug = document.slug
    if data.slug is not None:
        new_slug = _unique_document_slug(
            db, universe_id, data.slug, exclude_id=document.id
        )

    now = _now()
    result = db.execute(
        update(Document)
        .where(
            Document.id == document.id,
            Document.universe_id == universe_id,
            Document.version == data.expected_version,
            Document.deleted_at.is_(None),
        )
        .values(
            title=new_title,
            slug=new_slug,
            document_type=new_type,
            parent_id=new_parent.id if new_parent else None,
            content_json=new_content,
            status=new_status,
            visibility=new_visibility,
            sort_order=new_sort_order,
            updated_by=user.id,
            updated_at=now,
            version=Document.version + 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = _get_document_raw(db, universe_id, document_id)
        _version_conflict(data.expected_version, current)

    db.expire(document)
    db.refresh(document)

    if content_changed:
        _replace_entity_links(db, document, mentions)

    create_revision = (
        content_changed or data.checkpoint or (new_status == "published" and old_status != "published")
    )
    revision_number: int | None = None
    if create_revision:
        revision_number = _next_revision_number(db, document.id)
        if new_status == "published" and old_status != "published":
            source = "publish"
        elif content_changed:
            source = "manual"
        else:
            source = "checkpoint"
        db.add(
            DocumentRevision(
                id=uuid.uuid4(),
                document_id=document.id,
                revision_number=revision_number,
                content_json=document.content_json,
                markdown_snapshot=tiptap_to_markdown(document.content_json),
                change_summary=data.change_summary,
                source=source,
                created_by=user.id,
                created_at=now,
            )
        )

    record_audit(
        db,
        universe_id,
        user.id,
        "document.update",
        "document",
        document.id,
        before_hash=state_hash(before_state),
        after_hash=state_hash(_document_state(document)),
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "document.updated",
        "document",
        document.id,
        {
            "title": document.title,
            "status": document.status,
            "revision_number": revision_number,
        },
    )
    db.commit()
    return _document_detail(db, document, user, role)


def delete_document(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    _, membership = check_universe_access(
        db, universe_id, user, Action.DOCUMENT_DELETE
    )
    document = _get_visible_document(
        db, universe_id, document_id, user, membership.role
    )
    descendants: list[Document] = []
    frontier = [document.id]
    while frontier:
        children = list(
            db.scalars(
                select(Document).where(
                    Document.universe_id == universe_id,
                    Document.parent_id.in_(frontier),
                    Document.deleted_at.is_(None),
                )
            ).all()
        )
        if not children:
            break
        descendants.extend(children)
        frontier = [child.id for child in children]

    invisible = [
        child
        for child in descendants
        if not is_visible(child, user.id, membership.role)
    ]
    if invisible:
        raise ApiError(
            409,
            "document_has_inaccessible_children",
            "This document contains child documents you cannot access. Ask an administrator to delete it.",
            details={"inaccessible_children": len(invisible)},
        )

    ids = [document.id] + [child.id for child in descendants]
    before_state = _document_state(document)
    now = _now()
    db.execute(
        update(Document)
        .where(
            Document.id.in_(ids),
            Document.universe_id == universe_id,
            Document.deleted_at.is_(None),
        )
        .values(
            deleted_at=now,
            updated_at=now,
            updated_by=user.id,
            version=Document.version + 1,
        )
    )
    record_audit(
        db,
        universe_id,
        user.id,
        "document.delete",
        "document",
        document.id,
        before_hash=state_hash(before_state),
        after_hash=state_hash({"deleted": True, "descendant_count": len(descendants)}),
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "document.deleted",
        "document",
        document.id,
        {"title": document.title, "descendant_count": len(descendants)},
    )
    db.commit()


def restore_document(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> dict[str, Any]:
    _, membership = check_universe_access(
        db, universe_id, user, Action.DOCUMENT_RESTORE
    )
    document = _get_visible_document(
        db, universe_id, document_id, user, membership.role, include_deleted=True
    )
    if document.deleted_at is None:
        raise ApiError(409, "document_not_deleted", "This document is not deleted.")
    if document.parent_id is not None:
        parent = db.scalar(
            select(Document).where(
                Document.id == document.parent_id,
                Document.universe_id == universe_id,
            )
        )
        if parent is None or parent.deleted_at is not None:
            raise ApiError(
                409,
                "parent_deleted",
                "Restore the parent document before restoring this document.",
            )
    now = _now()
    result = db.execute(
        update(Document)
        .where(
            Document.id == document.id,
            Document.universe_id == universe_id,
            Document.deleted_at.is_not(None),
        )
        .values(
            deleted_at=None,
            updated_at=now,
            updated_by=user.id,
            version=Document.version + 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise ApiError(409, "document_not_deleted", "This document is not deleted.")
    db.expire(document)
    db.refresh(document)
    record_audit(
        db,
        universe_id,
        user.id,
        "document.restore",
        "document",
        document.id,
        after_hash=state_hash(_document_state(document)),
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "document.restored",
        "document",
        document.id,
        {"title": document.title},
    )
    db.commit()
    return _document_detail(db, document, user, membership.role)


# -----------------------------------------------------------------------------
# Revisions
# -----------------------------------------------------------------------------

def list_document_revisions(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
    *,
    include_content: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    _, membership = check_universe_access(db, universe_id, user, Action.DOCUMENT_READ)
    _get_visible_document(db, universe_id, document_id, user, membership.role)
    total = int(
        db.scalar(
            select(func.count(DocumentRevision.id)).where(
                DocumentRevision.document_id == document_id
            )
        )
        or 0
    )
    revisions = list(
        db.scalars(
            select(DocumentRevision)
            .where(DocumentRevision.document_id == document_id)
            .order_by(
                DocumentRevision.revision_number.desc(),
                DocumentRevision.id.asc(),
            )
            .limit(min(limit, 200))
            .offset(max(offset, 0))
        ).all()
    )
    return (
        [
            _revision_payload(revision, include_content=include_content)
            for revision in revisions
        ],
        total,
    )


def get_document_revision(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    revision_id: uuid.UUID,
    user: User,
) -> dict[str, Any]:
    _, membership = check_universe_access(db, universe_id, user, Action.DOCUMENT_READ)
    _get_visible_document(db, universe_id, document_id, user, membership.role)
    revision = db.scalar(
        select(DocumentRevision).where(
            DocumentRevision.id == revision_id,
            DocumentRevision.document_id == document_id,
        )
    )
    if revision is None:
        raise ApiError(404, "revision_not_found", "Document revision not found.")
    return _revision_payload(revision, include_content=True)


def restore_document_revision(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    revision_id: uuid.UUID,
    user: User,
    data: DocumentRestoreRequest,
    request_id: str | None = None,
) -> dict[str, Any]:
    _, membership = check_universe_access(
        db, universe_id, user, Action.DOCUMENT_RESTORE
    )
    document = _get_visible_document(
        db, universe_id, document_id, user, membership.role
    )
    revision = db.scalar(
        select(DocumentRevision).where(
            DocumentRevision.id == revision_id,
            DocumentRevision.document_id == document_id,
        )
    )
    if revision is None:
        raise ApiError(404, "revision_not_found", "Document revision not found.")
    expected_version = (
        data.expected_version
        if data.expected_version is not None
        else document.version
    )
    if document.version != expected_version:
        _version_conflict(expected_version, document)

    target_content = _normalise_content(revision.content_json)
    _validate_mentions(
        db,
        universe_id,
        target_content,
        user,
        membership.role,
        allow_deleted=True,
        enforce_visibility=False,
    )
    current_content = (
        document.content_json if isinstance(document.content_json, dict) else empty_document()
    )
    content_changed = state_hash(current_content) != state_hash(target_content)
    before_state = _document_state(document)
    now = _now()
    result = db.execute(
        update(Document)
        .where(
            Document.id == document.id,
            Document.universe_id == universe_id,
            Document.version == expected_version,
            Document.deleted_at.is_(None),
        )
        .values(
            content_json=target_content,
            updated_by=user.id,
            updated_at=now,
            version=Document.version + 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = _get_document_raw(db, universe_id, document_id)
        _version_conflict(expected_version, current)
    db.expire(document)
    db.refresh(document)

    if content_changed:
        reset_collaboration_state(db, universe_id, document.id)
        next_number = _next_revision_number(db, document.id)
        db.add(
            DocumentRevision(
                id=uuid.uuid4(),
                document_id=document.id,
                revision_number=next_number,
                content_json=current_content,
                markdown_snapshot=tiptap_to_markdown(current_content),
                change_summary=f"Snapshot before restoring revision {revision.revision_number}",
                source="checkpoint",
                created_by=user.id,
                created_at=now,
            )
        )
        mentions = extract_mentions(target_content)
        _replace_entity_links(db, document, mentions)
        restored_number = next_number + 1
    else:
        restored_number = _next_revision_number(db, document.id)
    db.add(
        DocumentRevision(
            id=uuid.uuid4(),
            document_id=document.id,
            revision_number=restored_number,
            content_json=target_content,
            markdown_snapshot=tiptap_to_markdown(target_content),
            change_summary=data.change_summary
            or f"Restored revision {revision.revision_number}",
            source="restore",
            created_by=user.id,
            created_at=now,
        )
    )
    record_audit(
        db,
        universe_id,
        user.id,
        "document.revision_restore",
        "document",
        document.id,
        before_hash=state_hash(before_state),
        after_hash=state_hash(_document_state(document)),
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "document.revision_restored",
        "document",
        document.id,
        {
            "title": document.title,
            "restored_revision": revision.revision_number,
            "revision_number": restored_number,
        },
    )
    db.commit()
    return _document_detail(db, document, user, membership.role)


# -----------------------------------------------------------------------------
# Entity links and backlinks
# -----------------------------------------------------------------------------

def list_document_links(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
) -> list[dict[str, Any]]:
    _, membership = check_universe_access(db, universe_id, user, Action.DOCUMENT_READ)
    document = _get_visible_document(
        db, universe_id, document_id, user, membership.role
    )
    return _document_entity_links(db, document, user, membership.role)


def list_entity_documents(
    db: Session,
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    user: User,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_READ)
    entity = db.scalar(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_(None),
        )
    )
    if entity is None or not is_visible(entity, user.id, membership.role):
        raise ApiError(404, "entity_not_found", "Entity not found.")

    predicates = [
        Document.universe_id == universe_id,
        Document.deleted_at.is_(None),
        DocumentEntityLink.entity_id == entity_id,
        Entity.universe_id == universe_id,
    ]
    visibility = visible_clause(Document, user.id, membership.role)
    if visibility is not None:
        predicates.append(visibility)
    base = (
        select(Document)
        .join(DocumentEntityLink, DocumentEntityLink.document_id == Document.id)
        .join(Entity, Entity.id == DocumentEntityLink.entity_id)
        .where(*predicates)
        .distinct()
    )
    total = int(
        db.scalar(
            select(func.count(func.distinct(Document.id)))
            .select_from(Document)
            .join(DocumentEntityLink, DocumentEntityLink.document_id == Document.id)
            .join(Entity, Entity.id == DocumentEntityLink.entity_id)
            .where(*predicates)
        )
        or 0
    )
    documents = list(
        db.scalars(
            base.order_by(Document.updated_at.desc(), Document.id.asc())
            .limit(min(limit, 200))
            .offset(max(offset, 0))
        ).all()
    )
    children = _has_children_map(
        db, universe_id, [document.id for document in documents]
    )
    return (
        [
            _document_summary(
                document, has_children=bool(children.get(document.id))
            )
            for document in documents
        ],
        total,
    )


# -----------------------------------------------------------------------------
# Comments
# -----------------------------------------------------------------------------

def _get_comment(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    comment_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> Comment:
    comment = db.scalar(
        select(Comment).where(
            Comment.id == comment_id,
            Comment.universe_id == universe_id,
            Comment.target_type == "document",
            Comment.target_id == document_id,
        )
    )
    if comment is None or (comment.deleted_at is not None and not include_deleted):
        raise ApiError(404, "comment_not_found", "Comment not found.")
    return comment


def _comment_payload(comment: Comment, display_name: str) -> dict[str, Any]:
    return {
        "id": comment.id,
        "universe_id": comment.universe_id,
        "target_type": comment.target_type,
        "target_id": comment.target_id,
        "parent_comment_id": comment.parent_comment_id,
        "body": comment.body,
        "anchor_json": comment.anchor_json,
        "created_by": comment.created_by,
        "author_display_name": display_name,
        "created_at": comment.created_at,
        "edited_at": comment.edited_at,
    }


def list_document_comments(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    _, membership = check_universe_access(db, universe_id, user, Action.DOCUMENT_READ)
    _get_visible_document(db, universe_id, document_id, user, membership.role)
    predicates = [
        Comment.universe_id == universe_id,
        Comment.target_type == "document",
        Comment.target_id == document_id,
        Comment.deleted_at.is_(None),
    ]
    total = int(
        db.scalar(select(func.count(Comment.id)).where(*predicates)) or 0
    )
    rows = db.execute(
        select(Comment, User.display_name)
        .join(User, User.id == Comment.created_by)
        .where(*predicates)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .limit(min(limit, 500))
        .offset(max(offset, 0))
    ).all()
    return (
        [_comment_payload(comment, display_name) for comment, display_name in rows],
        total,
    )


def create_document_comment(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
    data: CommentCreate,
    request_id: str | None = None,
) -> dict[str, Any]:
    _, membership = check_universe_access(
        db, universe_id, user, Action.DOCUMENT_COMMENT
    )
    _get_visible_document(db, universe_id, document_id, user, membership.role)
    body = _normalise_body(data.body)
    anchor = _normalise_comment_anchor(data.anchor_json)
    if data.parent_comment_id is not None:
        parent = _get_comment(
            db, universe_id, document_id, data.parent_comment_id
        )
        if parent.parent_comment_id is not None:
            _fail_validation(
                "parent_comment_id",
                "nested_reply_not_allowed",
                "Replies can only target a top-level comment.",
            )
    now = _now()
    comment = Comment(
        id=uuid.uuid4(),
        universe_id=universe_id,
        target_type="document",
        target_id=document_id,
        parent_comment_id=data.parent_comment_id,
        body=body,
        anchor_json=anchor,
        created_by=user.id,
        created_at=now,
    )
    db.add(comment)
    record_activity(
        db,
        universe_id,
        user.id,
        "document.comment_created",
        "document",
        document_id,
        {"comment_id": str(comment.id)},
    )
    db.commit()
    return _comment_payload(comment, user.display_name)


def update_document_comment(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    comment_id: uuid.UUID,
    user: User,
    data: CommentUpdate,
) -> dict[str, Any]:
    universe, membership = check_universe_access(
        db, universe_id, user, Action.DOCUMENT_READ
    )
    _ensure_mutable(universe)
    _get_visible_document(db, universe_id, document_id, user, membership.role)
    comment = _get_comment(db, universe_id, document_id, comment_id)
    if comment.created_by != user.id and not has_permission(
        membership.role, Action.DOCUMENT_COMMENT
    ):
        raise ApiError(
            403, "permission_denied", "You cannot edit this comment."
        )
    comment.body = _normalise_body(data.body)
    comment.edited_at = _now()
    record_activity(
        db,
        universe_id,
        user.id,
        "document.comment_updated",
        "document",
        document_id,
        {"comment_id": str(comment.id)},
    )
    db.commit()
    author = db.get(User, comment.created_by)
    return _comment_payload(comment, author.display_name if author else "Unknown")


def delete_document_comment(
    db: Session,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    comment_id: uuid.UUID,
    user: User,
) -> None:
    universe, membership = check_universe_access(
        db, universe_id, user, Action.DOCUMENT_READ
    )
    _ensure_mutable(universe)
    _get_visible_document(db, universe_id, document_id, user, membership.role)
    comment = _get_comment(db, universe_id, document_id, comment_id)
    if comment.created_by != user.id and not has_permission(
        membership.role, Action.DOCUMENT_DELETE
    ):
        raise ApiError(
            403, "permission_denied", "You cannot delete this comment."
        )
    now = _now()
    comment.deleted_at = now
    comment.edited_at = comment.edited_at or now
    db.execute(
        update(Comment)
        .where(
            Comment.universe_id == universe_id,
            Comment.target_type == "document",
            Comment.target_id == document_id,
            Comment.parent_comment_id == comment.id,
            Comment.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "document.comment_deleted",
        "document",
        document_id,
        {"comment_id": str(comment.id)},
    )
    db.commit()


# Re-exported for imports that historically used the markdown preview helper.
__all__ = [
    "ALLOWED_PARENT_TYPES",
    "DOCUMENT_STATUSES",
    "DOCUMENT_TYPES",
    "DOCUMENT_VISIBILITIES",
    "create_document",
    "create_document_comment",
    "delete_document",
    "delete_document_comment",
    "get_document_details",
    "get_document_revision",
    "get_document_tree",
    "list_document_comments",
    "list_document_links",
    "list_document_revisions",
    "list_documents",
    "list_entity_documents",
    "restore_document",
    "restore_document_revision",
    "update_document",
    "update_document_comment",
]
