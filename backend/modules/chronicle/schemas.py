from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DOCUMENT_TYPE_PATTERN = "^(collection|work|part|chapter|scene|note)$"
DOCUMENT_STATUS_PATTERN = "^(draft|review|published|archived)$"
DOCUMENT_VISIBILITY_PATTERN = "^(universe|restricted|draft|private)$"
REVISION_SOURCE_PATTERN = "^(manual|checkpoint|publish|restore|import)$"


# -----------------------------------------------------------------------------
# Documents
# -----------------------------------------------------------------------------

class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    document_type: str = Field(default="chapter", pattern=DOCUMENT_TYPE_PATTERN)
    parent_id: uuid.UUID | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    content_json: dict[str, Any] | None = None
    status: str = Field(default="draft", pattern=DOCUMENT_STATUS_PATTERN)
    visibility: str = Field(default="universe", pattern=DOCUMENT_VISIBILITY_PATTERN)
    sort_order: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    change_summary: str | None = Field(default=None, max_length=500)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    document_type: str | None = Field(default=None, pattern=DOCUMENT_TYPE_PATTERN)
    parent_id: uuid.UUID | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    content_json: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern=DOCUMENT_STATUS_PATTERN)
    visibility: str | None = Field(default=None, pattern=DOCUMENT_VISIBILITY_PATTERN)
    sort_order: int | None = Field(default=None, ge=-1_000_000, le=1_000_000)
    change_summary: str | None = Field(default=None, max_length=500)
    checkpoint: bool = False
    expected_version: int = Field(..., ge=1)


class DocumentPermissions(BaseModel):
    can_edit: bool
    can_delete: bool
    can_restore: bool
    can_comment: bool
    can_review: bool


class DocumentBreadcrumb(BaseModel):
    id: uuid.UUID
    title: str
    document_type: str


class DocumentEntityLinkResponse(BaseModel):
    entity_id: uuid.UUID
    title: str
    slug: str
    entity_type_key: str
    entity_type_name: str
    label: str
    link_kind: str
    mention_count: int
    entity_deleted: bool


class DocumentSummary(BaseModel):
    id: uuid.UUID
    universe_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    document_type: str
    title: str
    slug: str
    status: str
    visibility: str
    sort_order: int
    created_by: uuid.UUID
    updated_by: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime
    excerpt: str = ""
    has_children: bool = False


class DocumentResponse(DocumentSummary):
    content_json: dict[str, Any]
    current_revision_number: int = 0
    revision_count: int = 0
    breadcrumbs: list[DocumentBreadcrumb] = Field(default_factory=list)
    entity_links: list[DocumentEntityLinkResponse] = Field(default_factory=list)
    permissions: DocumentPermissions


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    total: int
    limit: int
    offset: int


class DocumentTreeNode(DocumentSummary):
    children: list[DocumentTreeNode] = Field(default_factory=list)


class DocumentTreeResponse(BaseModel):
    items: list[DocumentTreeNode]
    total: int


class DocumentRestoreRequest(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    change_summary: str | None = Field(default=None, max_length=500)


# -----------------------------------------------------------------------------
# Revisions
# -----------------------------------------------------------------------------

class DocumentRevisionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    revision_number: int
    content_json: dict[str, Any] | None = None
    markdown_snapshot: str | None = None
    change_summary: str | None = None
    source: str
    created_by: uuid.UUID
    created_at: datetime


class DocumentRevisionListResponse(BaseModel):
    items: list[DocumentRevisionResponse]
    total: int
    limit: int
    offset: int


# -----------------------------------------------------------------------------
# Comments
# -----------------------------------------------------------------------------

class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    parent_comment_id: uuid.UUID | None = None
    anchor_json: dict[str, Any] | None = None


class CommentUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)


class CommentResponse(BaseModel):
    id: uuid.UUID
    universe_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    parent_comment_id: uuid.UUID | None = None
    body: str
    anchor_json: dict[str, Any] | None = None
    created_by: uuid.UUID
    author_display_name: str
    created_at: datetime
    edited_at: datetime | None = None


class CommentListResponse(BaseModel):
    items: list[CommentResponse]
    total: int
    limit: int
    offset: int


DocumentTreeNode.model_rebuild()
