from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    String,
    Text,
    case,
    cast,
    func,
    literal,
    literal_column,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import Session

from backend.core.errors import ApiError
from backend.core.models import Document, Entity, EntityType, TimelineEvent, User
from backend.core.permissions import Action
from backend.core.visibility import visible_clause
from backend.modules.chronicle.content import content_preview
from backend.modules.search.schemas import SearchResult
from backend.modules.universes.service import check_universe_access

KINDS = frozenset({"entity", "document", "timeline_event"})
MAX_QUERY_LENGTH = 200
MAX_RESULT_LIMIT = 100
SNIPPET_LENGTH = 240


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_pattern(query: str) -> str:
    return f"%{_escape_like(query)}%"


def _highlight(text: str, query: str) -> tuple[str, int, int]:
    cleaned = " ".join(text.split())
    match = re.search(re.escape(query), cleaned, flags=re.IGNORECASE)
    if match is None:
        snippet = cleaned[:SNIPPET_LENGTH]
        return snippet, 0, 0
    start = match.start()
    left = max(0, start - SNIPPET_LENGTH // 3)
    right = min(len(cleaned), left + SNIPPET_LENGTH)
    left = max(0, right - SNIPPET_LENGTH)
    snippet = cleaned[left:right]
    return snippet, start - left, match.end() - left


def _rank_expression(title: Any, query: str, pattern: str) -> Any:
    return case(
        (func.lower(title) == query.casefold(), 0),
        (title.ilike(f"{_escape_like(query)}%", escape="\\"), 1),
        (title.ilike(pattern, escape="\\"), 2),
        else_=3,
    )


def _concat_columns(columns: list[Any]) -> Any:
    """Join text columns with single spaces using immutable operators.

    ``concat_ws`` is STABLE and therefore unusable inside an index
    expression; this ``||``/``coalesce`` chain mirrors migration
    ``0006_search_m7`` so the GIN indexes apply.
    """
    expression: Any = None
    for column in columns:
        piece = func.coalesce(column, literal_column("''"))
        expression = piece if expression is None else expression + literal_column("' '") + piece
    return expression


def _matches(
    db: Session,
    columns: list[Any],
    query: str,
    pattern: str,
    *,
    extra: list[Any] | None = None,
) -> Any:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # Keep this expression aligned with the GIN expression indexes in
        # migration 0006_search_m7: ``to_tsvector`` over an immutable ``||``
        # concatenation. Literal constants are intentional so PostgreSQL can
        # match the query expression to the index definition.
        vector = func.to_tsvector(
            literal_column("'simple'"),
            _concat_columns(columns),
        ).op("@@")(
            func.plainto_tsquery(literal_column("'simple'"), query)
        )
        if extra:
            return or_(vector, *(column.ilike(pattern, escape="\\") for column in extra))
        return vector
    return or_(*(column.ilike(pattern, escape="\\") for column in [*columns, *(extra or [])]))


def _entity_search_rows(db: Session, universe_id: uuid.UUID, user: User, role: str, term: str, pattern: str):
    visibility = visible_clause(Entity, user.id, role)
    predicates: list[Any] = [Entity.universe_id == universe_id, Entity.deleted_at.is_(None)]
    if visibility is not None:
        predicates.append(visibility)
    predicates.append(
        _matches(
            db,
            [Entity.title, Entity.summary, cast(Entity.custom_fields, Text)],
            term,
            pattern,
            extra=[EntityType.name],
        )
    )
    body = (
        func.coalesce(Entity.title, literal(""))
        + literal(" ")
        + func.coalesce(Entity.summary, literal(""))
        + literal(" ")
        + func.coalesce(cast(Entity.custom_fields, String), literal(""))
    )
    return (
        select(
            cast(Entity.id, String).label("id"),
            literal("entity").label("kind"),
            Entity.title.label("title"),
            body.label("body"),
            Entity.updated_at.label("updated_at"),
            _rank_expression(Entity.title, term, pattern).label("rank"),
        )
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(*predicates)
    )


def _document_search_rows(db: Session, universe_id: uuid.UUID, user: User, role: str, term: str, pattern: str):
    visibility = visible_clause(Document, user.id, role)
    predicates: list[Any] = [Document.universe_id == universe_id, Document.deleted_at.is_(None)]
    if visibility is not None:
        predicates.append(visibility)
    predicates.append(
        _matches(
            db,
            [Document.title, Document.slug, cast(Document.content_json, Text)],
            term,
            pattern,
        )
    )
    return select(
        cast(Document.id, String).label("id"),
        literal("document").label("kind"),
        Document.title.label("title"),
        cast(Document.content_json, String).label("body"),
        Document.updated_at.label("updated_at"),
        _rank_expression(Document.title, term, pattern).label("rank"),
    ).where(*predicates)


def _event_search_rows(db: Session, universe_id: uuid.UUID, term: str, pattern: str):
    predicates = [
        TimelineEvent.universe_id == universe_id,
        _matches(db, [TimelineEvent.title, TimelineEvent.description], term, pattern),
    ]
    body = (
        func.coalesce(TimelineEvent.title, literal(""))
        + literal(" ")
        + func.coalesce(TimelineEvent.description, literal(""))
    )
    return select(
        cast(TimelineEvent.id, String).label("id"),
        literal("timeline_event").label("kind"),
        TimelineEvent.title.label("title"),
        body.label("body"),
        TimelineEvent.updated_at.label("updated_at"),
        _rank_expression(TimelineEvent.title, term, pattern).label("rank"),
    ).where(*predicates)


def search_universe(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    *,
    query: str,
    kinds: list[str] | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    _, membership = check_universe_access(db, universe_id, user, Action.UNIVERSE_READ)
    term = " ".join(query.split())
    if len(term) < 2:
        raise ApiError(422, "search_query_too_short", "Search queries must contain at least 2 characters.")
    if len(term) > MAX_QUERY_LENGTH:
        raise ApiError(422, "search_query_too_long", "Search queries cannot exceed 200 characters.")
    selected = set(kinds or KINDS)
    if not selected or selected - KINDS:
        raise ApiError(422, "invalid_search_types", "Search types must be entity, document, or timeline_event.")

    pattern = _search_pattern(term)
    statements = []
    if "entity" in selected:
        statements.append(_entity_search_rows(db, universe_id, user, membership.role, term, pattern))
    if "document" in selected:
        statements.append(_document_search_rows(db, universe_id, user, membership.role, term, pattern))
    if "timeline_event" in selected:
        statements.append(_event_search_rows(db, universe_id, term, pattern))

    combined = union_all(*statements).subquery("search_results")
    total = int(db.scalar(select(func.count()).select_from(combined)) or 0)
    rows = db.execute(
        select(combined)
        .order_by(combined.c.rank, combined.c.updated_at.desc(), combined.c.title, combined.c.kind, combined.c.id)
        .limit(min(limit, MAX_RESULT_LIMIT))
        .offset(offset)
    ).all()

    # Decode Chronicle's canonical JSON only for the requested page, so search
    # results get readable prose rather than raw TipTap serialization.
    document_ids = [uuid.UUID(row.id) for row in rows if row.kind == "document"]
    document_text: dict[str, str] = {}
    if document_ids:
        documents = db.scalars(
            select(Document).where(
                Document.universe_id == universe_id,
                Document.id.in_(document_ids),
                Document.deleted_at.is_(None),
            )
        ).all()
        document_text = {
            str(document.id): content_preview(document.content_json, limit=50_000)
            for document in documents
        }

    results = []
    for row in rows:
        canonical_id = str(uuid.UUID(row.id))
        body = document_text.get(canonical_id, row.body or row.title)
        searchable_text = body if re.search(re.escape(term), body, flags=re.IGNORECASE) else row.title
        snippet, highlight_start, highlight_end = _highlight(searchable_text, term)
        if row.kind == "entity":
            href = f"/universes/{universe_id}?tab=codex&entity={canonical_id}"
        elif row.kind == "document":
            href = f"/universes/{universe_id}/chronicle/{canonical_id}"
        else:
            href = f"/universes/{universe_id}?tab=chronos&event={canonical_id}"
        results.append({
            "id": canonical_id,
            "kind": row.kind,
            "title": row.title,
            "summary": snippet,
            "snippet": snippet,
            "highlight_start": highlight_start,
            "highlight_end": highlight_end,
            "href": href,
            "updated_at": row.updated_at.isoformat(),
        })
    return results, total
