from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.models import User
from backend.modules.identity.service import get_current_account
from backend.modules.universes.schemas import (
    ActivityEventResponse,
    AuditLogResponse,
    InvitationCreate,
    InvitationResponse,
    MemberResponse,
    MemberUpdate,
    OwnershipTransfer,
    UniverseCreate,
    UniverseListResponse,
    UniverseResponse,
    UniverseUpdate,
)
from backend.modules.universes.service import (
    accept_invitation,
    archive_universe,
    create_invitation,
    create_universe,
    get_universe_details,
    list_activity_events,
    list_audit_logs,
    list_invitations,
    list_members,
    list_user_universes,
    remove_member,
    revoke_invitation,
    transfer_ownership,
    unarchive_universe,
    update_member_role,
    update_universe,
)

router = APIRouter(prefix="/api/v1", tags=["universes"])


@router.get("/universes", response_model=UniverseListResponse)
def list_universes(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> UniverseListResponse:
    user = get_current_account(request, db)
    items = list_user_universes(db, user, limit=limit)
    return UniverseListResponse(
        items=[UniverseResponse.model_validate(u) for u in items],
        total=len(items),
    )


@router.post("/universes", response_model=UniverseResponse, status_code=201)
def create_new_universe(
    payload: UniverseCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> UniverseResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    result = create_universe(db, user, payload, request_id=request_id)
    return UniverseResponse.model_validate(result)


@router.get("/universes/{universe_id}", response_model=UniverseResponse)
def get_universe(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> UniverseResponse:
    user = get_current_account(request, db)
    result = get_universe_details(db, universe_id, user)
    return UniverseResponse.model_validate(result)


@router.patch("/universes/{universe_id}", response_model=UniverseResponse)
def modify_universe(
    universe_id: uuid.UUID,
    payload: UniverseUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> UniverseResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    result = update_universe(db, universe_id, user, payload, request_id=request_id)
    return UniverseResponse.model_validate(result)


@router.post("/universes/{universe_id}/archive", response_model=UniverseResponse)
def archive_existing_universe(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> UniverseResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    result = archive_universe(db, universe_id, user, request_id=request_id)
    return UniverseResponse.model_validate(result)


@router.post("/universes/{universe_id}/unarchive", response_model=UniverseResponse)
def unarchive_existing_universe(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> UniverseResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    result = unarchive_universe(db, universe_id, user, request_id=request_id)
    return UniverseResponse.model_validate(result)


@router.post(
    "/universes/{universe_id}/transfer-ownership",
    response_model=UniverseResponse,
)
def transfer_universe_ownership(
    universe_id: uuid.UUID,
    payload: OwnershipTransfer,
    request: Request,
    db: Session = Depends(get_db),
) -> UniverseResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    result = transfer_ownership(
        db,
        universe_id,
        user,
        payload.new_owner_user_id,
        request_id=request_id,
    )
    return UniverseResponse.model_validate(result)


# -----------------------------------------------------------------------------
# Society & Memberships
# -----------------------------------------------------------------------------

@router.get("/universes/{universe_id}/members", response_model=list[MemberResponse])
def get_universe_members(
    universe_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[MemberResponse]:
    user = get_current_account(request, db)
    results = list_members(db, universe_id, user, limit=limit)
    return [MemberResponse.model_validate(m) for m in results]


@router.patch("/universes/{universe_id}/members/{target_user_id}", response_model=MemberResponse)
def modify_member_role(
    universe_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: MemberUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> MemberResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    result = update_member_role(
        db, universe_id, user, target_user_id, payload.role, request_id=request_id
    )
    return MemberResponse.model_validate(result)


@router.delete("/universes/{universe_id}/members/{target_user_id}", status_code=204)
def remove_universe_member(
    universe_id: uuid.UUID,
    target_user_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    remove_member(db, universe_id, user, target_user_id, request_id=request_id)
    return Response(status_code=204)


# -----------------------------------------------------------------------------
# Invitations
# -----------------------------------------------------------------------------

@router.post(
    "/universes/{universe_id}/invitations",
    response_model=InvitationResponse,
    status_code=201,
)
def invite_user_to_universe(
    universe_id: uuid.UUID,
    payload: InvitationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> InvitationResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    invitation, raw_token = create_invitation(
        db, universe_id, user, str(payload.email), payload.role, request_id=request_id
    )
    resp = InvitationResponse.model_validate(invitation)
    resp.invitation_token = raw_token
    return resp


@router.get(
    "/universes/{universe_id}/invitations",
    response_model=list[InvitationResponse],
)
def get_pending_invitations(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> list[InvitationResponse]:
    user = get_current_account(request, db)
    results = list_invitations(db, universe_id, user)
    return [InvitationResponse.model_validate(invitation) for invitation in results]


@router.delete(
    "/universes/{universe_id}/invitations/{invitation_id}",
    status_code=204,
)
def revoke_universe_invitation(
    universe_id: uuid.UUID,
    invitation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    revoke_invitation(
        db, universe_id, invitation_id, user, request_id=request_id
    )
    return Response(status_code=204)


@router.post("/invitations/{token}/accept", response_model=UniverseResponse)
def accept_universe_invitation(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> UniverseResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    universe = accept_invitation(db, user, token, request_id=request_id)
    return UniverseResponse.model_validate(get_universe_details(db, universe.id, user))


# -----------------------------------------------------------------------------
# Audit & Activity
# -----------------------------------------------------------------------------

@router.get("/universes/{universe_id}/audit-logs", response_model=list[AuditLogResponse])
def get_audit_trail(
    universe_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[AuditLogResponse]:
    user = get_current_account(request, db)
    results = list_audit_logs(db, universe_id, user, limit=limit)
    return [AuditLogResponse.model_validate(a) for a in results]


@router.get("/universes/{universe_id}/activity", response_model=list[ActivityEventResponse])
def get_activity_feed(
    universe_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ActivityEventResponse]:
    user = get_current_account(request, db)
    results = list_activity_events(db, universe_id, user, limit=limit)
    return [ActivityEventResponse.model_validate(a) for a in results]
