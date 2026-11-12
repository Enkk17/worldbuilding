from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------------
# Entity Types
# -----------------------------------------------------------------------------

class CustomFieldDefinition(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=80)
    type: str = Field(
        ...,
        pattern="^(text|long_text|number|boolean|date|enum|multi_enum|url|entity_reference)$",
    )
    required: bool = False
    options: list[str] = Field(default_factory=list)  # for enum / multi_enum
    default_value: Any = None
    target_entity_type_key: str | None = None  # for entity_reference


class EntityTypeCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    key: str = Field(..., min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    schema_json: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=32)


class EntityTypeUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    schema_json: dict[str, Any] | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=32)


class EntityTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    universe_id: uuid.UUID
    key: str
    name: str
    description: str | None = None
    schema_json: dict[str, Any]
    icon: str | None = None
    color: str | None = None
    is_system: bool = False
    created_at: datetime
    updated_at: datetime


# -----------------------------------------------------------------------------
# Relation Types
# -----------------------------------------------------------------------------

class RelationTypeCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    label: str = Field(..., min_length=1, max_length=80)
    inverse_label: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    allowed_source_types: list[str] = Field(default_factory=list)
    allowed_target_types: list[str] = Field(default_factory=list)
    is_directional: bool = True
    is_symmetric: bool = False


class RelationTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    key: str
    label: str
    inverse_label: str | None = None
    description: str | None = None
    allowed_source_types: list[str]
    allowed_target_types: list[str]
    is_directional: bool
    is_symmetric: bool
    created_at: datetime


# -----------------------------------------------------------------------------
# Entities
# -----------------------------------------------------------------------------

class EntityCreate(BaseModel):
    entity_type_key: str
    title: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=1000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active", pattern="^(active|draft|archived)$")
    visibility: str = Field(default="universe", pattern="^(universe|restricted|private)$")
    tags: list[str] = Field(default_factory=list)


class EntityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=1000)
    custom_fields: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(active|draft|archived)$")
    visibility: str | None = Field(default=None, pattern="^(universe|restricted|private)$")
    tags: list[str] | None = None
    expected_version: int = Field(..., ge=1)  # Optimistic concurrency precondition


class EntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    entity_type_id: uuid.UUID
    entity_type_key: str
    entity_type_name: str
    title: str
    slug: str
    summary: str | None = None
    custom_fields: dict[str, Any]
    status: str
    visibility: str
    created_by: uuid.UUID
    updated_by: uuid.UUID
    version: int
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EntityListResponse(BaseModel):
    items: list[EntityResponse]
    total: int


# -----------------------------------------------------------------------------
# Entity Relations
# -----------------------------------------------------------------------------

class EntityRelationCreate(BaseModel):
    source_entity_id: uuid.UUID
    relation_type_key: str
    target_entity_id: uuid.UUID
    attributes_json: dict[str, Any] = Field(default_factory=dict)


class EntityRelationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    source_entity_id: uuid.UUID
    source_entity_title: str
    relation_type_id: uuid.UUID
    relation_type_key: str
    relation_label: str
    inverse_label: str | None = None
    is_symmetric: bool = False
    target_entity_id: uuid.UUID
    target_entity_title: str
    attributes_json: dict[str, Any]
    created_by: uuid.UUID
    created_at: datetime


# -----------------------------------------------------------------------------
# Nexus Graph
# -----------------------------------------------------------------------------

class GraphNode(BaseModel):
    id: str
    title: str
    entity_type_key: str
    entity_type_name: str
    summary: str | None = None
    color: str | None = None
    icon: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation_type_key: str
    label: str
    inverse_label: str | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
