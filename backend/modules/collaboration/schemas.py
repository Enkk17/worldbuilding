from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class CollaborationTicketResponse(BaseModel):
    ticket: str = Field(min_length=32, max_length=4096)
    document_id: uuid.UUID
    universe_id: uuid.UUID
    websocket_path: str
    protocol: str
    expires_at: int
    can_write: bool
    role: str
    display_name: str
    collab_generation: int
