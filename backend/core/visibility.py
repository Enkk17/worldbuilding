"""Shared resource-visibility policy.

The M0 specification defines four visibility levels for universe content:

* ``universe``: every active member may read it;
* ``restricted``: privileged roles and the creator may read it (explicit grants
  are not implemented in v1.0, so this is the conservative fallback);
* ``draft``: creator, editors, admins, and owners;
* ``private``: creator, admins, and owners.

Keeping the predicate in one place avoids the classic tenant bug where one
listing endpoint forgets the visibility filter and leaks titles or metadata.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from backend.core.permissions import Role

PRIVILEGED_ROLES = frozenset({Role.OWNER.value, Role.ADMIN.value})
DRAFT_ROLES = frozenset({Role.EDITOR.value})


def visible_clause(
    model: Any, user_id: uuid.UUID, role: str
) -> ColumnElement[bool] | None:
    """Return an SQL predicate restricting rows to resources the actor may read.

    ``None`` means the role sees everything in the universe.
    """

    if role in PRIVILEGED_ROLES:
        return None
    clauses = [
        model.visibility == "universe",
        model.created_by == user_id,
    ]
    if role in DRAFT_ROLES:
        clauses.append(model.visibility.in_(("restricted", "draft")))
    return or_(*clauses)


def is_visible(resource: Any, user_id: uuid.UUID, role: str) -> bool:
    if role in PRIVILEGED_ROLES:
        return True
    visibility = getattr(resource, "visibility", "universe")
    if visibility == "universe":
        return True
    if getattr(resource, "created_by", None) == user_id:
        return True
    if role in DRAFT_ROLES and visibility in {"restricted", "draft"}:
        return True
    return False
