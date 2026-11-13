from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MapCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    image_asset_id: uuid.UUID | None = None
    width: int = Field(default=1920, ge=1, le=100_000)
    height: int = Field(default=1080, ge=1, le=100_000)


class MapUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    image_asset_id: uuid.UUID | None = None
    width: int | None = Field(default=None, ge=1, le=100_000)
    height: int | None = Field(default=None, ge=1, le=100_000)
    expected_version: int = Field(ge=1)


class MapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    title: str
    description: str | None
    image_asset_id: uuid.UUID | None
    coordinate_system: str
    width: int
    height: int
    created_by: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime


class MapListResponse(BaseModel):
    items: list[MapResponse]
    total: int


class MapPoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class MapMarkerCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    x_norm: float = Field(ge=0, le=1)
    y_norm: float = Field(ge=0, le=1)
    marker_type: str = Field(default="poi", min_length=1, max_length=64)
    linked_entity_id: uuid.UUID | None = None
    style_json: dict[str, Any] = Field(default_factory=dict)


class MapMarkerUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    x_norm: float | None = Field(default=None, ge=0, le=1)
    y_norm: float | None = Field(default=None, ge=0, le=1)
    marker_type: str | None = Field(default=None, min_length=1, max_length=64)
    linked_entity_id: uuid.UUID | None = None
    style_json: dict[str, Any] | None = None
    expected_version: int = Field(ge=1)


class MapMarkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    map_id: uuid.UUID
    universe_id: uuid.UUID
    title: str
    description: str | None
    x_norm: float
    y_norm: float
    marker_type: str
    linked_entity_id: uuid.UUID | None
    style_json: dict[str, Any]
    created_by: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime


class MapMarkerListResponse(BaseModel):
    items: list[MapMarkerResponse]
    total: int


class PolygonGeometry(BaseModel):
    type: Literal["polygon"] = "polygon"
    points: list[MapPoint] = Field(min_length=3, max_length=200)


class MapRegionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    geometry_json: PolygonGeometry
    linked_entity_id: uuid.UUID | None = None
    style_json: dict[str, Any] = Field(default_factory=dict)


class MapRegionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    geometry_json: PolygonGeometry | None = None
    linked_entity_id: uuid.UUID | None = None
    style_json: dict[str, Any] | None = None
    expected_version: int = Field(ge=1)


class MapRegionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    map_id: uuid.UUID
    universe_id: uuid.UUID
    title: str
    geometry_json: dict[str, Any]
    linked_entity_id: uuid.UUID | None
    style_json: dict[str, Any]
    version: int
    created_at: datetime


class MapRegionListResponse(BaseModel):
    items: list[MapRegionResponse]
    total: int


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    original_filename: str
    mime_type: str
    byte_size: int
    checksum_sha256: str
    width: int | None
    height: int | None
    uploaded_by: uuid.UUID
    created_at: datetime
    download_path: str
