"""Authorization and lifecycle helpers for collaboration rooms."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.core.models import (
    AccountSession,
    Document,
    Universe,
    UniverseMember,
    User,
)
from backend.core.visibility import is_visible
from backend.modules.chronicle.service import can_edit_document
from backend.modules.collaboration.tickets import issue_ticket
from backend.modules.universes.service import get_membership


_ACCESS_MESSAGES = {
    "authentication_required": "Authentication is required.",
    "universe_not_found": (
        "The requested universe does not exist or access is denied."
    ),
    "document_not_found": (
        "The requested document does not exist or access is denied."
    ),
}


class CollaborationAccessError(ApiError):
    """Durable authorization failure, mapped by the global API handler."""

    def __init__(self, code: str, *, status_code: int = 404) -> None:
        super().__init__(
            status_code,
            code,
            _ACCESS_MESSAGES.get(code, "Access is denied."),
        )


@dataclass(frozen=True, slots=True)
class CollaborationAccess:
    user: User
    session: AccountSession
    universe: Universe
    membership: UniverseMember
    document: Document
    can_write: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_is_active(session: AccountSession | None) -> bool:
    if session is None or session.revoked_at is not None:
        return False
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > _now()


def load_access(
    db: Session,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> CollaborationAccess:
    """Re-authorise a room participant from durable state.

    This function is intentionally independent from the original ticket
    payload: the ticket only identifies the actor, session and document.
    Membership, visibility, document state and write permission are always
    re-read so a role change or removal takes effect on an open connection.
    """

    session = db.get(AccountSession, session_id)
    if not _session_is_active(session) or session.user_id != user_id:
        raise CollaborationAccessError("authentication_required", status_code=401)
    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise CollaborationAccessError("authentication_required", status_code=401)

    universe = db.get(Universe, universe_id)
    if universe is None or universe.status == "deleted":
        raise CollaborationAccessError("universe_not_found")
    membership = get_membership(db, universe_id, user_id)
    if membership is None:
        raise CollaborationAccessError("universe_not_found")

    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.universe_id == universe_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None or not is_visible(
        document, user_id, membership.role
    ):
        raise CollaborationAccessError("document_not_found")

    can_write = (
        universe.status == "active"
        and can_edit_document(user, membership.role, document)
    )
    return CollaborationAccess(
        user=user,
        session=session,
        universe=universe,
        membership=membership,
        document=document,
        can_write=can_write,
    )


def issue_collaboration_ticket(
    db: Session,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User,
    session: AccountSession,
    settings: Settings,
) -> dict[str, object]:
    access = load_access(
        db,
        universe_id=universe_id,
        document_id=document_id,
        user_id=user.id,
        session_id=session.id,
    )
    ticket = issue_ticket(
        secret=settings.collaboration_ticket_secret,
        ttl_seconds=settings.collaboration_ticket_ttl_seconds,
        user_id=user.id,
        session_id=session.id,
        universe_id=universe_id,
        document_id=document_id,
        display_name=user.display_name,
        can_write=access.can_write,
        collab_generation=access.document.collab_generation,
    )
    return {
        "ticket": ticket.token,
        "document_id": document_id,
        "universe_id": universe_id,
        "websocket_path": f"/api/v1/collaboration/documents/{document_id}",
        "protocol": "yjs-websocket-v1",
        "expires_at": ticket.expires_at,
        "can_write": access.can_write,
        "role": access.membership.role,
        "display_name": user.display_name,
        "collab_generation": access.document.collab_generation,
    }
