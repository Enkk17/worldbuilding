from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UniverseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class UniverseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    settings_json: dict[str, Any] | None = None
    cover_asset_id: uuid.UUID | None = None


class UniverseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    owner_user_id: uuid.UUID
    cover_asset_id: uuid.UUID | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)
    role: str = "viewer"
    status: str
    created_at: datetime
    updated_at: datetime


class UniverseListResponse(BaseModel):
    items: list[UniverseResponse]
    total: int


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    status: str
    joined_at: datetime


class MemberUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|editor|contributor|viewer)$")


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = Field(default="viewer", pattern="^(admin|editor|contributor|viewer)$")


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime
    invitation_token: str | None = None


class OwnershipTransfer(BaseModel):
    new_owner_user_id: uuid.UUID


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: uuid.UUID | None
    before_hash: str | None = None
    after_hash: str | None = None
    request_id: str | None = None
    created_at: datetime


class ActivityEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    actor_user_id: uuid.UUID
    event_type: str
    target_type: str
    target_id: uuid.UUID | None
    metadata_json: dict[str, Any]
    created_at: datetime
