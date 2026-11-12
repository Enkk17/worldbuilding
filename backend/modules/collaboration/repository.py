"""Durable storage operations for collaboration rooms.

All functions are synchronous and are invoked from the event loop through
``starlette.concurrency.run_in_threadpool``. Keeping SQLAlchemy sessions out of
the WebSocket coroutine prevents accidental cross-thread use of a Session.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.core.models import (
    Document,
    DocumentCollabSnapshot,
    DocumentCollabUpdate,
)
from backend.modules.chronicle.service import (
    apply_collaborative_content,
    reset_collaboration_state,
)
from backend.modules.collaboration.service import CollaborationAccessError

SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StaleRoomError(RuntimeError):
    """The room generation no longer matches durable document state."""


def load_room_payload(
    session_factory: SessionFactory,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    with session_factory() as db:
        document = db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.universe_id == universe_id,
                Document.deleted_at.is_(None),
            )
        )
        if document is None:
            raise CollaborationAccessError("document_not_found")

        snapshot = db.scalar(
            select(DocumentCollabSnapshot)
            .where(
                DocumentCollabSnapshot.document_id == document_id,
                DocumentCollabSnapshot.universe_id == universe_id,
            )
            .order_by(
                DocumentCollabSnapshot.created_at.desc(),
                DocumentCollabSnapshot.id.desc(),
            )
            .limit(1)
        )
        last_sequence = snapshot.last_update_sequence if snapshot else 0
        update_rows = db.scalars(
            select(DocumentCollabUpdate)
            .where(
                DocumentCollabUpdate.document_id == document_id,
                DocumentCollabUpdate.universe_id == universe_id,
                DocumentCollabUpdate.sequence > last_sequence,
            )
            .order_by(DocumentCollabUpdate.sequence.asc())
        ).all()
        max_sequence = db.scalar(
            select(func.max(DocumentCollabUpdate.sequence)).where(
                DocumentCollabUpdate.document_id == document_id,
                DocumentCollabUpdate.universe_id == universe_id,
            )
        )
        return {
            "content_json": document.content_json,
            "owner_id": document.created_by,
            "collab_generation": document.collab_generation,
            "has_snapshot": snapshot is not None,
            "snapshot_state": snapshot.ydoc_state if snapshot else None,
            "snapshot_vector": snapshot.state_vector if snapshot else None,
            "snapshot_sequence": last_sequence,
            "updates": [
                (row.sequence, row.update_blob, row.actor_id)
                for row in update_rows
            ],
            "max_sequence": int(max_sequence or last_sequence),
        }


def persist_baseline_snapshot(
    session_factory: SessionFactory,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    ydoc_state: bytes,
    state_vector: bytes,
    expected_generation: int,
) -> uuid.UUID:
    with session_factory() as db:
        document = db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.universe_id == universe_id,
                Document.deleted_at.is_(None),
            )
        )
        if document is None:
            raise CollaborationAccessError("document_not_found")
        if document.collab_generation != expected_generation:
            raise StaleRoomError("collaboration generation changed")
        snapshot = DocumentCollabSnapshot(
            id=uuid.uuid4(),
            universe_id=universe_id,
            document_id=document_id,
            ydoc_state=ydoc_state,
            state_vector=state_vector,
            last_update_sequence=0,
            update_count=0,
            reason="baseline",
            created_by=None,
            created_at=_now(),
        )
        db.add(snapshot)
        db.commit()
        return snapshot.id


def persist_update_batch(
    session_factory: SessionFactory,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    expected_generation: int,
    rows: list[dict[str, Any]],
) -> None:
    with session_factory() as db:
        document = db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.universe_id == universe_id,
                Document.deleted_at.is_(None),
            )
        )
        if document is None:
            raise CollaborationAccessError("document_not_found")
        if document.collab_generation != expected_generation:
            raise StaleRoomError("collaboration generation changed")
        now = _now()
        for row in rows:
            db.add(
                DocumentCollabUpdate(
                    id=uuid.uuid4(),
                    universe_id=universe_id,
                    document_id=document_id,
                    sequence=row["sequence"],
                    update_blob=row["update"],
                    client_id=row.get("client_id"),
                    actor_id=row.get("actor_id"),
                    byte_size=len(row["update"]),
                    created_at=now,
                )
            )
        db.commit()


def persist_snapshot_and_prune(
    session_factory: SessionFactory,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    expected_generation: int,
    ydoc_state: bytes,
    state_vector: bytes,
    last_update_sequence: int,
    update_count: int,
    created_by: uuid.UUID | None,
    reason: str = "compaction",
) -> None:
    """Insert a verified snapshot and delete only the covered update log.

    The caller verifies that applying ``ydoc_state`` reproduces the room's
    state vector before invoking this function. Insert and delete share one
    transaction: a crash never leaves a gap between retained updates and the
    snapshot that covers them.
    """

    with session_factory() as db:
        document = db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.universe_id == universe_id,
                Document.deleted_at.is_(None),
            )
        )
        if document is None:
            raise CollaborationAccessError("document_not_found")
        if document.collab_generation != expected_generation:
            raise StaleRoomError("collaboration generation changed")
        db.add(
            DocumentCollabSnapshot(
                id=uuid.uuid4(),
                universe_id=universe_id,
                document_id=document_id,
                ydoc_state=ydoc_state,
                state_vector=state_vector,
                last_update_sequence=last_update_sequence,
                update_count=update_count,
                reason=reason,
                created_by=created_by,
                created_at=_now(),
            )
        )
        db.execute(
            delete(DocumentCollabUpdate).where(
                DocumentCollabUpdate.document_id == document_id,
                DocumentCollabUpdate.universe_id == universe_id,
                DocumentCollabUpdate.sequence <= last_update_sequence,
            )
        )
        db.commit()


def materialize_room(
    session_factory: SessionFactory,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    expected_generation: int,
    actor_id: uuid.UUID,
    role: str,
    content_json: dict[str, Any],
    create_revision: bool,
) -> dict[str, Any] | None:
    with session_factory() as db:
        return apply_collaborative_content(
            db,
            universe_id,
            document_id,
            actor_id,
            role,
            content_json,
            expected_generation=expected_generation,
            create_revision=create_revision,
            change_summary="Automatic collaboration checkpoint"
            if create_revision
            else None,
        )


def reset_room_state(
    session_factory: SessionFactory,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
) -> int | None:
    with session_factory() as db:
        generation = reset_collaboration_state(
            db, universe_id, document_id
        )
        db.commit()
        return generation
