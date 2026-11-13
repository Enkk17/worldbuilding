from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.errors import ApiError
from backend.modules.exports.importer import (
    list_import_jobs,
    run_import,
    validate_import_bundle,
    summarise,
)
from backend.modules.exports.exporter import export_universe
from backend.modules.exports.schemas import (
    ImportJobListResponse,
    ImportJobResponse,
    ImportReport,
    ImportValidationResponse,
)
from backend.modules.identity.service import get_current_account

router = APIRouter(prefix="/api/v1", tags=["import-export"])


@router.post(
    "/universes/{universe_id}/exports",
    responses={
        200: {
            "description": "A downloadable WORLDWEAVE export bundle.",
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def create_universe_export(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    settings = request.app.state.settings
    payload, manifest, _filename = export_universe(
        db,
        universe_id,
        user,
        media_root=settings.media_root,
        request_id=getattr(request.state, "request_id", None),
    )
    filename = f"worldweave-{manifest['universe_slug']}-export.zip"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Export-Schema-Version": str(manifest["schema_version"]),
            "X-Export-Manifest": json.dumps(manifest, separators=(",", ":")),
        },
    )


@router.post(
    "/universes/{universe_id}/imports/validate",
    response_model=ImportValidationResponse,
)
async def validate_universe_import(
    universe_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportValidationResponse:
    user = get_current_account(request, db)
    settings = request.app.state.settings
    payload = await file.read(settings.max_archive_bytes + 1)
    try:
        bundle, actions = validate_import_bundle(
            db,
            universe_id,
            user,
            payload,
            max_bytes=settings.max_archive_bytes,
        )
    finally:
        await file.close()
    report = summarise(actions)
    return ImportValidationResponse(
        valid=report["valid"],
        schema_version=int(bundle.manifest.get("schema_version") or 1),
        source_universe_id=bundle.source_universe_id,
        source_universe_name=bundle.universe.get("name"),
        report=ImportReport.model_validate(report),
        warnings=bundle.warnings,
    )


@router.post(
    "/universes/{universe_id}/imports",
    response_model=ImportJobResponse,
    status_code=201,
)
async def execute_universe_import(
    universe_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    conflict_policy: Annotated[str, Query(pattern="^(skip|overwrite|fail)$")] = "skip",
    dry_run: Annotated[bool, Query()] = False,
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    user = get_current_account(request, db)
    settings = request.app.state.settings
    payload = await file.read(settings.max_archive_bytes + 1)
    try:
        job = run_import(
            db,
            universe_id,
            user,
            payload,
            conflict_policy=conflict_policy,
            dry_run=dry_run,
            media_root=settings.media_root,
            max_bytes=settings.max_archive_bytes,
            request_id=getattr(request.state, "request_id", None),
        )
    finally:
        await file.close()
    return ImportJobResponse.model_validate(job)


@router.get(
    "/universes/{universe_id}/imports",
    response_model=ImportJobListResponse,
)
def get_import_jobs(
    universe_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ImportJobListResponse:
    user = get_current_account(request, db)
    jobs = list_import_jobs(db, universe_id, user, limit=limit)
    return ImportJobListResponse(
        items=[ImportJobResponse.model_validate(job) for job in jobs],
        total=len(jobs),
    )
