from __future__ import annotations

from enum import Enum
from typing import Final

class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"

class Action:
    # Universe
    UNIVERSE_READ = "universe.read"
    UNIVERSE_UPDATE = "universe.update"
    UNIVERSE_ARCHIVE = "universe.archive"
    UNIVERSE_DELETE = "universe.delete"

    # Member & Society
    MEMBER_READ = "member.read"
    MEMBER_INVITE = "member.invite"
    MEMBER_UPDATE_ROLE = "member.update_role"
    MEMBER_REMOVE = "member.remove"

    # Codex (Entities & Relations)
    ENTITY_READ = "entity.read"
    ENTITY_CREATE = "entity.create"
    ENTITY_UPDATE = "entity.update"
    ENTITY_DELETE = "entity.delete"
    ENTITY_RESTORE = "entity.restore"
    ENTITY_PUBLISH = "entity.publish"
    ENTITY_TYPE_MANAGE = "entity_type.manage"
    RELATION_CREATE = "relation.create"
    RELATION_DELETE = "relation.delete"

    # Chronicle (Documents & Comments)
    DOCUMENT_READ = "document.read"
    DOCUMENT_CREATE = "document.create"
    DOCUMENT_UPDATE = "document.update"
    DOCUMENT_DELETE = "document.delete"
    DOCUMENT_RESTORE = "document.restore"
    DOCUMENT_COMMENT = "document.comment"
    DOCUMENT_REVIEW = "document.review"

    # Atlas (Maps & Markers)
    MAP_READ = "map.read"
    MAP_CREATE = "map.create"
    MAP_UPDATE = "map.update"
    MAP_DELETE = "map.delete"

    # Chronos (Timeline & Calendars)
    TIMELINE_READ = "timeline.read"
    TIMELINE_CREATE = "timeline.create"
    TIMELINE_UPDATE = "timeline.update"
    TIMELINE_DELETE = "timeline.delete"

    # Import / Export
    EXPORT_CREATE = "export.create"
    IMPORT_VALIDATE = "import.validate"
    IMPORT_EXECUTE = "import.execute"

    # Audit
    AUDIT_READ = "audit.read"

# Permission definitions per role
ROLE_PERMISSIONS: Final[dict[Role, set[str]]] = {
    Role.OWNER: {
        Action.UNIVERSE_READ,
        Action.UNIVERSE_UPDATE,
        Action.UNIVERSE_ARCHIVE,
        Action.UNIVERSE_DELETE,
        Action.MEMBER_READ,
        Action.MEMBER_INVITE,
        Action.MEMBER_UPDATE_ROLE,
        Action.MEMBER_REMOVE,
        Action.ENTITY_READ,
        Action.ENTITY_CREATE,
        Action.ENTITY_UPDATE,
        Action.ENTITY_DELETE,
        Action.ENTITY_RESTORE,
        Action.ENTITY_PUBLISH,
        Action.ENTITY_TYPE_MANAGE,
        Action.RELATION_CREATE,
        Action.RELATION_DELETE,
        Action.DOCUMENT_READ,
        Action.DOCUMENT_CREATE,
        Action.DOCUMENT_UPDATE,
        Action.DOCUMENT_DELETE,
        Action.DOCUMENT_RESTORE,
        Action.DOCUMENT_COMMENT,
        Action.DOCUMENT_REVIEW,
        Action.MAP_READ,
        Action.MAP_CREATE,
        Action.MAP_UPDATE,
        Action.MAP_DELETE,
        Action.TIMELINE_READ,
        Action.TIMELINE_CREATE,
        Action.TIMELINE_UPDATE,
        Action.TIMELINE_DELETE,
        Action.EXPORT_CREATE,
        Action.IMPORT_VALIDATE,
        Action.IMPORT_EXECUTE,
        Action.AUDIT_READ,
    },
    Role.ADMIN: {
        Action.UNIVERSE_READ,
        Action.UNIVERSE_UPDATE,
        Action.UNIVERSE_ARCHIVE,
        Action.MEMBER_READ,
        Action.MEMBER_INVITE,
        Action.MEMBER_UPDATE_ROLE,
        Action.MEMBER_REMOVE,
        Action.ENTITY_READ,
        Action.ENTITY_CREATE,
        Action.ENTITY_UPDATE,
        Action.ENTITY_DELETE,
        Action.ENTITY_RESTORE,
        Action.ENTITY_PUBLISH,
        Action.ENTITY_TYPE_MANAGE,
        Action.RELATION_CREATE,
        Action.RELATION_DELETE,
        Action.DOCUMENT_READ,
        Action.DOCUMENT_CREATE,
        Action.DOCUMENT_UPDATE,
        Action.DOCUMENT_DELETE,
        Action.DOCUMENT_RESTORE,
        Action.DOCUMENT_COMMENT,
        Action.DOCUMENT_REVIEW,
        Action.MAP_READ,
        Action.MAP_CREATE,
        Action.MAP_UPDATE,
        Action.MAP_DELETE,
        Action.TIMELINE_READ,
        Action.TIMELINE_CREATE,
        Action.TIMELINE_UPDATE,
        Action.TIMELINE_DELETE,
        Action.EXPORT_CREATE,
        Action.IMPORT_VALIDATE,
        Action.IMPORT_EXECUTE,
        Action.AUDIT_READ,
    },
    Role.EDITOR: {
        Action.UNIVERSE_READ,
        Action.MEMBER_READ,
        Action.ENTITY_READ,
        Action.ENTITY_CREATE,
        Action.ENTITY_UPDATE,
        Action.ENTITY_DELETE,
        Action.ENTITY_RESTORE,
        Action.ENTITY_PUBLISH,
        Action.RELATION_CREATE,
        Action.RELATION_DELETE,
        Action.DOCUMENT_READ,
        Action.DOCUMENT_CREATE,
        Action.DOCUMENT_UPDATE,
        Action.DOCUMENT_DELETE,
        Action.DOCUMENT_RESTORE,
        Action.DOCUMENT_COMMENT,
        Action.DOCUMENT_REVIEW,
        Action.MAP_READ,
        Action.MAP_CREATE,
        Action.MAP_UPDATE,
        Action.MAP_DELETE,
        Action.TIMELINE_READ,
        Action.TIMELINE_CREATE,
        Action.TIMELINE_UPDATE,
        Action.TIMELINE_DELETE,
        Action.EXPORT_CREATE,
    },
    Role.CONTRIBUTOR: {
        Action.UNIVERSE_READ,
        Action.MEMBER_READ,
        Action.ENTITY_READ,
        Action.ENTITY_CREATE,
        Action.DOCUMENT_READ,
        Action.DOCUMENT_CREATE,
        Action.DOCUMENT_COMMENT,
        Action.MAP_READ,
        Action.TIMELINE_READ,
    },
    Role.VIEWER: {
        Action.UNIVERSE_READ,
        Action.MEMBER_READ,
        Action.ENTITY_READ,
        Action.DOCUMENT_READ,
        Action.MAP_READ,
        Action.TIMELINE_READ,
    },
}

ROLE_RANK: Final[dict[str, int]] = {
    Role.OWNER.value: 50,
    Role.ADMIN.value: 40,
    Role.EDITOR.value: 30,
    Role.CONTRIBUTOR.value: 20,
    Role.VIEWER.value: 10,
}

def has_permission(role: str, action: str) -> bool:
    try:
        r = Role(role)
    except ValueError:
        return False
    return action in ROLE_PERMISSIONS.get(r, set())

def can_manage_member(actor_role: str, target_current_role: str, target_new_role: str | None = None) -> bool:
    actor_rank = ROLE_RANK.get(actor_role, 0)
    target_rank = ROLE_RANK.get(target_current_role, 0)

    # Cannot manage someone of equal or higher rank unless owner managing owner
    if actor_role != Role.OWNER.value and target_rank >= actor_rank:
        return False

    if target_new_role is not None:
        new_rank = ROLE_RANK.get(target_new_role, 0)
        # Cannot promote to rank equal or higher than self
        if actor_role != Role.OWNER.value and new_rank >= actor_rank:
            return False

    return True
