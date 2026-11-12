from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ApiError
from backend.core.models import (
    ActivityEvent,
    Asset,
    AuditLog,
    Invitation,
    Universe,
    UniverseMember,
    User,
)
from backend.core.permissions import (
    Action,
    Role,
    can_manage_member,
    has_permission,
)
from backend.core.security import state_hash, token_hash
from backend.modules.universes.schemas import UniverseCreate, UniverseUpdate

READ_ONLY_ACTIONS = frozenset(
    {
        Action.UNIVERSE_READ,
        Action.MEMBER_READ,
        Action.ENTITY_READ,
        Action.DOCUMENT_READ,
        Action.MAP_READ,
        Action.TIMELINE_READ,
        Action.AUDIT_READ,
    }
)


def _universe_payload(universe: Universe, role: str) -> dict[str, Any]:
    return {
        "id": universe.id,
        "name": universe.name,
        "slug": universe.slug,
        "description": universe.description,
        "owner_user_id": universe.owner_user_id,
        "cover_asset_id": universe.cover_asset_id,
        "settings_json": universe.settings_json or {},
        "role": role,
        "status": universe.status,
        "created_at": universe.created_at,
        "updated_at": universe.updated_at,
    }


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    slug = re.sub(r"[-\s]+", "-", cleaned)
    return slug or "universe"


def record_audit(
    db: Session,
    universe_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        id=uuid.uuid4(),
        universe_id=universe_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_hash=before_hash,
        after_hash=after_hash,
        request_id=request_id,
    )
    db.add(entry)
    return entry


def record_activity(
    db: Session,
    universe_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    event_type: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> ActivityEvent:
    entry = ActivityEvent(
        id=uuid.uuid4(),
        universe_id=universe_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        metadata_json=metadata or {},
    )
    db.add(entry)
    return entry


def get_membership(
    db: Session, universe_id: uuid.UUID, user_id: uuid.UUID
) -> UniverseMember | None:
    return db.scalar(
        select(UniverseMember).where(
            UniverseMember.universe_id == universe_id,
            UniverseMember.user_id == user_id,
            UniverseMember.status == "active",
        )
    )


def check_universe_access(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    required_action: str | None = None,
) -> tuple[Universe, UniverseMember]:
    universe = db.get(Universe, universe_id)
    if universe is None or universe.status == "deleted":
        raise ApiError(404, "universe_not_found", "The requested universe does not exist.")

    membership = get_membership(db, universe_id, user.id)
    if membership is None:
        raise ApiError(404, "universe_not_found", "The requested universe does not exist or access is denied.")

    if required_action and not has_permission(membership.role, required_action):
        raise ApiError(403, "permission_denied", f"Role '{membership.role}' lacks permission for '{required_action}'.")

    if (
        universe.status == "archived"
        and required_action is not None
        and required_action not in READ_ONLY_ACTIONS
    ):
        raise ApiError(
            409,
            "universe_archived",
            "This universe is archived and read-only. Restore it before making changes.",
        )

    return universe, membership


def create_universe(
    db: Session,
    user: User,
    data: UniverseCreate,
    request_id: str | None = None,
) -> dict[str, Any]:
    base_slug = slugify(data.slug or data.name)
    slug = base_slug
    counter = 1
    while db.scalar(select(Universe.id).where(Universe.slug == slug)) is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1

    universe = Universe(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name=data.name.strip(),
        slug=slug,
        description=data.description.strip() if data.description else None,
        settings_json={},
        status="active",
    )
    db.add(universe)
    db.flush()

    membership = UniverseMember(
        id=uuid.uuid4(),
        universe_id=universe.id,
        user_id=user.id,
        role=Role.OWNER.value,
        status="active",
        joined_at=datetime.now(timezone.utc),
    )
    db.add(membership)

    record_audit(
        db,
        universe.id,
        user.id,
        "universe.create",
        "universe",
        universe.id,
        request_id=request_id,
    )
    record_activity(
        db,
        universe.id,
        user.id,
        "universe.created",
        "universe",
        universe.id,
        {"name": universe.name, "slug": universe.slug},
    )
    db.commit()

    return _universe_payload(universe, Role.OWNER.value)


def list_user_universes(
    db: Session, user: User, limit: int = 100
) -> list[dict[str, Any]]:
    stmt = (
        select(Universe, UniverseMember.role)
        .join(UniverseMember, UniverseMember.universe_id == Universe.id)
        .where(
            UniverseMember.user_id == user.id,
            UniverseMember.status == "active",
            Universe.status != "deleted",
        )
        .order_by(Universe.updated_at.desc())
        .limit(min(limit, 200))
    )
    results = db.execute(stmt).all()
    return [_universe_payload(u, role) for u, role in results]


def get_universe_details(
    db: Session, universe_id: uuid.UUID, user: User
) -> dict[str, Any]:
    universe, membership = check_universe_access(db, universe_id, user, Action.UNIVERSE_READ)
    return _universe_payload(universe, membership.role)


def update_universe(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    data: UniverseUpdate,
    request_id: str | None = None,
) -> dict[str, Any]:
    universe, membership = check_universe_access(db, universe_id, user, Action.UNIVERSE_UPDATE)

    before = {
        "name": universe.name,
        "description": universe.description,
        "cover_asset_id": str(universe.cover_asset_id) if universe.cover_asset_id else None,
        "settings_json": universe.settings_json,
    }

    if data.name is not None:
        universe.name = data.name.strip()
    if "description" in data.model_fields_set:
        universe.description = data.description.strip() if data.description else None
    if data.settings_json is not None:
        universe.settings_json = {**(universe.settings_json or {}), **data.settings_json}
    if "cover_asset_id" in data.model_fields_set:
        if data.cover_asset_id is not None:
            asset = db.get(Asset, data.cover_asset_id)
            if (
                asset is None
                or asset.universe_id != universe_id
                or asset.deleted_at is not None
            ):
                raise ApiError(
                    400,
                    "invalid_cover_asset",
                    "The cover asset must be an active asset in this universe.",
                )
        universe.cover_asset_id = data.cover_asset_id

    universe.updated_at = datetime.now(timezone.utc)
    after = {
        "name": universe.name,
        "description": universe.description,
        "cover_asset_id": str(universe.cover_asset_id) if universe.cover_asset_id else None,
        "settings_json": universe.settings_json,
    }
    record_audit(
        db,
        universe.id,
        user.id,
        Action.UNIVERSE_UPDATE,
        "universe",
        universe.id,
        before_hash=state_hash(before),
        after_hash=state_hash(after),
        request_id=request_id,
    )
    record_activity(
        db,
        universe.id,
        user.id,
        "universe.updated",
        "universe",
        universe.id,
        {"name": universe.name},
    )
    db.commit()

    return _universe_payload(universe, membership.role)


def archive_universe(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> dict[str, Any]:
    universe, membership = check_universe_access(
        db, universe_id, user, Action.UNIVERSE_READ
    )
    if not has_permission(membership.role, Action.UNIVERSE_ARCHIVE):
        raise ApiError(
            403,
            "permission_denied",
            f"Role '{membership.role}' cannot archive this universe.",
        )

    if universe.status != "archived":
        universe.status = "archived"
        universe.updated_at = datetime.now(timezone.utc)
        record_audit(
            db,
            universe.id,
            user.id,
            Action.UNIVERSE_ARCHIVE,
            "universe",
            universe.id,
            before_hash=state_hash({"status": "active"}),
            after_hash=state_hash({"status": "archived"}),
            request_id=request_id,
        )
        record_activity(
            db,
            universe.id,
            user.id,
            "universe.archived",
            "universe",
            universe.id,
        )
        db.commit()
    return _universe_payload(universe, membership.role)


def unarchive_universe(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> dict[str, Any]:
    universe, membership = check_universe_access(
        db, universe_id, user, Action.UNIVERSE_READ
    )
    if not has_permission(membership.role, Action.UNIVERSE_ARCHIVE):
        raise ApiError(
            403,
            "permission_denied",
            f"Role '{membership.role}' cannot restore this universe.",
        )

    if universe.status == "archived":
        universe.status = "active"
        universe.updated_at = datetime.now(timezone.utc)
        record_audit(
            db,
            universe.id,
            user.id,
            "universe.unarchive",
            "universe",
            universe.id,
            before_hash=state_hash({"status": "archived"}),
            after_hash=state_hash({"status": "active"}),
            request_id=request_id,
        )
        record_activity(
            db,
            universe.id,
            user.id,
            "universe.restored",
            "universe",
            universe.id,
        )
        db.commit()
    return _universe_payload(universe, membership.role)


def list_members(
    db: Session, universe_id: uuid.UUID, user: User, limit: int = 100
) -> list[dict[str, Any]]:
    check_universe_access(db, universe_id, user, Action.MEMBER_READ)
    stmt = (
        select(UniverseMember, User.email, User.display_name)
        .join(User, User.id == UniverseMember.user_id)
        .where(
            UniverseMember.universe_id == universe_id,
            UniverseMember.status == "active",
        )
        .order_by(UniverseMember.joined_at.asc())
        .limit(min(limit, 200))
    )
    results = db.execute(stmt).all()
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "email": email,
            "display_name": display_name,
            "role": m.role,
            "status": m.status,
            "joined_at": m.joined_at,
        }
        for m, email, display_name in results
    ]


def update_member_role(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    target_user_id: uuid.UUID,
    new_role: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    universe, actor_membership = check_universe_access(
        db, universe_id, user, Action.MEMBER_UPDATE_ROLE
    )

    target_membership = get_membership(db, universe_id, target_user_id)
    if target_membership is None:
        raise ApiError(404, "member_not_found", "Member not found in this universe.")

    if target_user_id == universe.owner_user_id:
        raise ApiError(
            400,
            "cannot_change_owner_role",
            "Ownership must be transferred explicitly; the owner role cannot be changed directly.",
        )

    if not can_manage_member(actor_membership.role, target_membership.role, new_role):
        raise ApiError(
            403,
            "insufficient_authority",
            "Cannot modify role of equal or higher ranking member.",
        )

    previous_role = target_membership.role
    if previous_role != new_role:
        target_membership.role = new_role
        record_audit(
            db,
            universe_id,
            user.id,
            Action.MEMBER_UPDATE_ROLE,
            "member",
            target_membership.id,
            before_hash=state_hash({"role": previous_role}),
            after_hash=state_hash({"role": new_role}),
            request_id=request_id,
        )
        record_activity(
            db,
            universe_id,
            user.id,
            "member.role_changed",
            "member",
            target_membership.id,
            {"from": previous_role, "to": new_role},
        )
        db.commit()

    target_user = db.get(User, target_user_id)
    return {
        "id": target_membership.id,
        "user_id": target_membership.user_id,
        "email": target_user.email if target_user else "",
        "display_name": target_user.display_name if target_user else "",
        "role": target_membership.role,
        "status": target_membership.status,
        "joined_at": target_membership.joined_at,
    }


def remove_member(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    target_user_id: uuid.UUID,
    request_id: str | None = None,
) -> None:
    universe, actor_membership = check_universe_access(
        db, universe_id, user, Action.MEMBER_REMOVE
    )

    if target_user_id == universe.owner_user_id:
        raise ApiError(400, "cannot_remove_owner", "The universe owner cannot be removed.")

    target_membership = get_membership(db, universe_id, target_user_id)
    if target_membership is None:
        raise ApiError(404, "member_not_found", "Member not found in this universe.")

    if not can_manage_member(actor_membership.role, target_membership.role):
        raise ApiError(
            403,
            "insufficient_authority",
            "Cannot remove equal or higher ranking member.",
        )

    removed_role = target_membership.role
    removed_membership_id = target_membership.id
    db.delete(target_membership)
    record_audit(
        db,
        universe_id,
        user.id,
        Action.MEMBER_REMOVE,
        "member",
        removed_membership_id,
        before_hash=state_hash({"role": removed_role}),
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "member.removed",
        "user",
        target_user_id,
        {"role": removed_role},
    )
    db.commit()


def create_invitation(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    email: str,
    role: str,
    request_id: str | None = None,
) -> tuple[Invitation, str]:
    _universe, actor_membership = check_universe_access(
        db, universe_id, user, Action.MEMBER_INVITE
    )

    if not can_manage_member(actor_membership.role, role, role):
        raise ApiError(
            403,
            "insufficient_authority",
            "Cannot invite with role equal to or higher than your own.",
        )

    normalized_email = email.strip().lower()
    now = datetime.now(timezone.utc)

    existing_member = db.scalar(
        select(UniverseMember.id)
        .join(User, User.id == UniverseMember.user_id)
        .where(
            UniverseMember.universe_id == universe_id,
            UniverseMember.status == "active",
            User.email == normalized_email,
        )
    )
    if existing_member is not None:
        raise ApiError(
            409,
            "already_member",
            "This account is already an active member of the universe.",
        )

    pending = db.scalar(
        select(Invitation.id).where(
            Invitation.universe_id == universe_id,
            Invitation.email == normalized_email,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > now,
        )
    )
    if pending is not None:
        raise ApiError(
            409,
            "invitation_pending",
            "A pending invitation already exists for this email. Revoke it before creating a new one.",
        )

    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        id=uuid.uuid4(),
        universe_id=universe_id,
        email=normalized_email,
        role=role,
        token_hash=token_hash(token),
        expires_at=now + timedelta(days=7),
        created_by=user.id,
    )
    db.add(invitation)
    record_audit(
        db,
        universe_id,
        user.id,
        Action.MEMBER_INVITE,
        "invitation",
        invitation.id,
        after_hash=state_hash({"email": normalized_email, "role": role}),
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "member.invited",
        "invitation",
        invitation.id,
        {"role": role},
    )
    db.commit()
    return invitation, token


def accept_invitation(
    db: Session,
    user: User,
    raw_token: str,
    request_id: str | None = None,
) -> Universe:
    now = datetime.now(timezone.utc)
    h = token_hash(raw_token)
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.token_hash == h,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > now,
        )
    )
    if invitation is None:
        raise ApiError(404, "invitation_invalid", "Invitation is invalid or has expired.")

    if invitation.email.lower() != user.email.lower():
        raise ApiError(
            403,
            "invitation_email_mismatch",
            "This invitation was issued to a different email address.",
        )

    universe = db.get(Universe, invitation.universe_id)
    if universe is None or universe.status == "deleted":
        raise ApiError(404, "invitation_invalid", "Invitation is invalid or has expired.")
    if universe.status == "archived":
        raise ApiError(
            409,
            "universe_archived",
            "This universe is archived and cannot accept new members.",
        )

    # Check if already a member
    existing = get_membership(db, invitation.universe_id, user.id)
    if existing is not None:
        invitation.accepted_at = now
        db.commit()
        return universe

    membership = UniverseMember(
        id=uuid.uuid4(),
        universe_id=invitation.universe_id,
        user_id=user.id,
        role=invitation.role,
        status="active",
        invited_by=invitation.created_by,
        joined_at=now,
    )
    db.add(membership)
    invitation.accepted_at = now
    record_audit(
        db,
        invitation.universe_id,
        user.id,
        "member.join",
        "member",
        membership.id,
        request_id=request_id,
    )
    record_activity(
        db,
        invitation.universe_id,
        user.id,
        "member.joined",
        "user",
        user.id,
        {"role": invitation.role},
    )
    db.commit()
    return universe


def list_invitations(
    db: Session, universe_id: uuid.UUID, user: User
) -> list[Invitation]:
    check_universe_access(db, universe_id, user, Action.MEMBER_INVITE)
    stmt = (
        select(Invitation)
        .where(Invitation.universe_id == universe_id)
        .order_by(Invitation.created_at.desc())
        .limit(100)
    )
    return list(db.scalars(stmt).all())


def revoke_invitation(
    db: Session,
    universe_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    check_universe_access(db, universe_id, user, Action.MEMBER_INVITE)
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.universe_id == universe_id,
        )
    )
    if invitation is None:
        raise ApiError(404, "invitation_not_found", "Invitation not found.")
    if invitation.accepted_at is not None:
        raise ApiError(
            409,
            "invitation_already_accepted",
            "An accepted invitation cannot be revoked.",
        )

    db.delete(invitation)
    record_audit(
        db,
        universe_id,
        user.id,
        "invitation.revoke",
        "invitation",
        invitation_id,
        request_id=request_id,
    )
    db.commit()


def transfer_ownership(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    new_owner_user_id: uuid.UUID,
    request_id: str | None = None,
) -> dict[str, Any]:
    universe, actor_membership = check_universe_access(
        db, universe_id, user, Action.UNIVERSE_READ
    )
    if actor_membership.role != Role.OWNER.value:
        raise ApiError(
            403,
            "owner_required",
            "Only the current owner can transfer ownership.",
        )
    if new_owner_user_id == universe.owner_user_id:
        raise ApiError(
            400,
            "owner_unchanged",
            "The selected account is already the owner.",
        )

    new_owner_membership = get_membership(db, universe_id, new_owner_user_id)
    if new_owner_membership is None:
        raise ApiError(
            404,
            "member_not_found",
            "The new owner must be an active member of this universe.",
        )

    old_owner_id = universe.owner_user_id
    old_owner_membership = get_membership(db, universe_id, old_owner_id)
    if old_owner_membership is None:
        raise ApiError(
            409,
            "owner_membership_missing",
            "The current owner has no active membership record.",
        )

    old_owner_membership.role = Role.ADMIN.value
    new_owner_membership.role = Role.OWNER.value
    universe.owner_user_id = new_owner_user_id
    universe.updated_at = datetime.now(timezone.utc)

    record_audit(
        db,
        universe_id,
        user.id,
        "universe.transfer_ownership",
        "universe",
        universe_id,
        before_hash=state_hash({"owner_user_id": str(old_owner_id)}),
        after_hash=state_hash({"owner_user_id": str(new_owner_user_id)}),
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "universe.ownership_transferred",
        "universe",
        universe_id,
        {"previous_owner_user_id": str(old_owner_id)},
    )
    db.commit()
    return _universe_payload(universe, Role.ADMIN.value)


def list_audit_logs(
    db: Session, universe_id: uuid.UUID, user: User, limit: int = 50
) -> list[AuditLog]:
    check_universe_access(db, universe_id, user, Action.AUDIT_READ)
    stmt = (
        select(AuditLog)
        .where(AuditLog.universe_id == universe_id)
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 100))
    )
    return list(db.scalars(stmt).all())


def list_activity_events(
    db: Session, universe_id: uuid.UUID, user: User, limit: int = 50
) -> list[ActivityEvent]:
    check_universe_access(db, universe_id, user, Action.UNIVERSE_READ)
    stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.universe_id == universe_id)
        .order_by(ActivityEvent.created_at.desc())
        .limit(min(limit, 100))
    )
    return list(db.scalars(stmt).all())
