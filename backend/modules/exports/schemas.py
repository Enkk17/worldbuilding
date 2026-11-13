from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExportCounts(BaseModel):
    entity_types: int = 0
    relation_types: int = 0
    entities: int = 0
    relations: int = 0
    documents: int = 0
    maps: int = 0
    calendars: int = 0
    timeline_events: int = 0
    assets: int = 0


class ExportManifest(BaseModel):
    format: str
    schema_version: int
    exporter_version: str
    universe_id: uuid.UUID
    universe_name: str
    universe_slug: str
    exported_at: str
    counts: ExportCounts
    warnings: list[str] = Field(default_factory=list)


class ImportReportItem(BaseModel):
    kind: str
    id: str | None = None
    label: str
    action: Literal["create", "update", "skip", "conflict", "error"]
    message: str | None = None


class ImportReport(BaseModel):
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    items: list[ImportReportItem] = Field(default_factory=list)
    errors: int = 0
    valid: bool = True


class ImportValidationResponse(BaseModel):
    valid: bool
    schema_version: int
    source_universe_id: uuid.UUID | None = None
    source_universe_name: str | None = None
    report: ImportReport
    warnings: list[str] = Field(default_factory=list)


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    source_universe_id: uuid.UUID | None = None
    schema_version: int
    status: str
    conflict_policy: str
    dry_run: bool
    archive_checksum_sha256: str
    report_json: dict[str, Any]
    warnings_json: list[Any]
    created_by: uuid.UUID
    created_at: datetime


class ImportJobListResponse(BaseModel):
    items: list[ImportJobResponse]
    total: int
