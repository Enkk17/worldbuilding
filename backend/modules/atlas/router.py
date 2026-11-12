from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.models import User
from backend.modules.atlas.schemas import (
    AssetResponse,
    MapCreate,
    MapListResponse,
    MapMarkerCreate,
    MapMarkerListResponse,
    MapMarkerResponse,
    MapMarkerUpdate,
    MapRegionCreate,
    MapRegionListResponse,
    MapRegionResponse,
    MapResponse,
    MapUpdate,
)
from backend.modules.atlas.service import (
    create_map,
    create_marker,
    create_region,
    delete_map,
    delete_marker,
    get_asset,
    get_map,
    list_maps,
    list_markers,
    list_regions,
    update_map,
    update_marker,
)
from backend.modules.atlas.storage import create_asset, get_asset_for_download
from backend.modules.identity.service import get_current_account

router = APIRouter(prefix="/api/v1", tags=["atlas"])


@router.get("/universes/{universe_id}/maps", response_model=MapListResponse)
def get_maps(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MapListResponse:
    user = get_current_account(request, db)
    items, total = list_maps(db, universe_id, user, limit, offset)
    return MapListResponse(items=items, total=total)


@router.post(
    "/universes/{universe_id}/maps",
    response_model=MapResponse,
    status_code=201,
)
def create_new_map(
    universe_id: uuid.UUID,
    payload: MapCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> MapResponse:
    user = get_current_account(request, db)
    record = create_map(
        db,
        universe_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return MapResponse.model_validate(record)


@router.get("/universes/{universe_id}/maps/{map_id}", response_model=MapResponse)
def get_map_detail(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> MapResponse:
    user = get_current_account(request, db)
    return MapResponse.model_validate(get_map(db, universe_id, map_id, user))


@router.patch("/universes/{universe_id}/maps/{map_id}", response_model=MapResponse)
def update_map_detail(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    payload: MapUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> MapResponse:
    user = get_current_account(request, db)
    record = update_map(
        db,
        universe_id,
        map_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return MapResponse.model_validate(record)


@router.delete(
    "/universes/{universe_id}/maps/{map_id}",
    status_code=204,
    response_class=Response,
)
def delete_map_detail(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    delete_map(
        db,
        universe_id,
        map_id,
        user,
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=204)


@router.get(
    "/universes/{universe_id}/maps/{map_id}/markers",
    response_model=MapMarkerListResponse,
)
def get_map_markers(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> MapMarkerListResponse:
    user = get_current_account(request, db)
    items, total = list_markers(db, universe_id, map_id, user)
    return MapMarkerListResponse(items=items, total=total)


@router.post(
    "/universes/{universe_id}/maps/{map_id}/markers",
    response_model=MapMarkerResponse,
    status_code=201,
)
def create_map_marker(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    payload: MapMarkerCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> MapMarkerResponse:
    user = get_current_account(request, db)
    record = create_marker(
        db,
        universe_id,
        map_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return MapMarkerResponse.model_validate(record)


@router.patch(
    "/universes/{universe_id}/maps/{map_id}/markers/{marker_id}",
    response_model=MapMarkerResponse,
)
def update_map_marker(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    marker_id: uuid.UUID,
    payload: MapMarkerUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> MapMarkerResponse:
    user = get_current_account(request, db)
    record = update_marker(
        db,
        universe_id,
        map_id,
        marker_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return MapMarkerResponse.model_validate(record)


@router.delete(
    "/universes/{universe_id}/maps/{map_id}/markers/{marker_id}",
    status_code=204,
    response_class=Response,
)
def delete_map_marker(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    marker_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    delete_marker(
        db,
        universe_id,
        map_id,
        marker_id,
        user,
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=204)


@router.get(
    "/universes/{universe_id}/maps/{map_id}/regions",
    response_model=MapRegionListResponse,
)
def get_map_regions(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> MapRegionListResponse:
    user = get_current_account(request, db)
    items, total = list_regions(db, universe_id, map_id, user)
    return MapRegionListResponse(items=items, total=total)


@router.post(
    "/universes/{universe_id}/maps/{map_id}/regions",
    response_model=MapRegionResponse,
    status_code=201,
)
def create_map_region(
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    payload: MapRegionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> MapRegionResponse:
    user = get_current_account(request, db)
    record = create_region(
        db,
        universe_id,
        map_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return MapRegionResponse.model_validate(record)


@router.post(
    "/universes/{universe_id}/assets",
    response_model=AssetResponse,
    status_code=201,
)
async def upload_universe_asset(
    universe_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> AssetResponse:
    user = get_current_account(request, db)
    settings = request.app.state.settings
    payload = await file.read(settings.max_asset_bytes + 1)
    try:
        record = create_asset(
            db=db,
            user=user,
            universe_id=universe_id,
            payload=payload,
            filename=file.filename,
            media_root=settings.media_root,
            max_bytes=settings.max_asset_bytes,
            request_id=getattr(request.state, "request_id", None),
        )
    finally:
        await file.close()
    return AssetResponse(
        id=record.id,
        universe_id=record.universe_id,
        original_filename=record.original_filename,
        mime_type=record.mime_type,
        byte_size=record.byte_size,
        checksum_sha256=record.checksum_sha256,
        width=record.width,
        height=record.height,
        uploaded_by=record.uploaded_by,
        created_at=record.created_at,
        download_path=f"/api/v1/assets/{record.id}",
    )


@router.get("/universes/{universe_id}/assets/{asset_id}", response_model=AssetResponse)
def get_asset_metadata(
    universe_id: uuid.UUID,
    asset_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> AssetResponse:
    user = get_current_account(request, db)
    record = get_asset(db, universe_id, asset_id, user)
    return AssetResponse(
        id=record.id,
        universe_id=record.universe_id,
        original_filename=record.original_filename,
        mime_type=record.mime_type,
        byte_size=record.byte_size,
        checksum_sha256=record.checksum_sha256,
        width=record.width,
        height=record.height,
        uploaded_by=record.uploaded_by,
        created_at=record.created_at,
        download_path=f"/api/v1/assets/{record.id}",
    )


@router.get("/assets/{asset_id}", include_in_schema=False)
def download_asset(
    asset_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_account(request, db)
    asset, path = get_asset_for_download(
        db, asset_id, user, request.app.state.settings.media_root
    )
    return FileResponse(
        path,
        media_type=asset.mime_type,
        filename=asset.original_filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
