from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, WebSocket
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.modules.collaboration.schemas import CollaborationTicketResponse
from backend.modules.collaboration.service import issue_collaboration_ticket
from backend.modules.identity.service import (
    get_active_session,
    get_current_account,
)

router = APIRouter(prefix="/api/v1", tags=["collaboration"])


@router.get(
    "/universes/{universe_id}/documents/{document_id}/collaboration-ticket",
    response_model=CollaborationTicketResponse,
)
def get_collaboration_ticket(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> CollaborationTicketResponse:
    user = get_current_account(request, db)
    session = get_active_session(request, db)
    data = issue_collaboration_ticket(
        db,
        universe_id=universe_id,
        document_id=document_id,
        user=user,
        session=session,
        settings=request.app.state.settings,
    )
    return CollaborationTicketResponse.model_validate(data)


@router.websocket("/collaboration/documents/{document_id}")
async def collaborate_on_document(
    websocket: WebSocket,
    document_id: uuid.UUID,
    ticket: str = Query(default="", max_length=4096),
) -> None:
    manager = getattr(websocket.app.state, "collaboration_manager", None)
    if manager is None:
        await websocket.close(code=1011, reason="collaboration_unavailable")
        return
    await manager.handle_websocket(
        websocket, document_id=document_id, ticket=ticket
    )
