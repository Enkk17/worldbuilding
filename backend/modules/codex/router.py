from __future__ import annotations

import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.models import User
from backend.modules.identity.service import get_current_account
from backend.modules.codex.schemas import (
    EntityCreate,
    EntityListResponse,
    EntityRelationCreate,
    EntityRelationResponse,
    EntityResponse,
    EntityTypeCreate,
    EntityTypeResponse,
    EntityTypeUpdate,
    EntityUpdate,
    GraphResponse,
    RelationTypeCreate,
    RelationTypeResponse,
)
from backend.modules.codex.service import (
    create_entity,
    create_entity_type,
    create_relation,
    create_relation_type,
    delete_entity,
    delete_relation,
    get_entity_details,
    list_entities,
    list_entity_relations,
    list_entity_types,
    list_relation_types,
    query_graph,
    restore_entity,
    update_entity,
    update_entity_type,
)

router = APIRouter(prefix="/api/v1", tags=["codex"])


# -----------------------------------------------------------------------------
# Entity Types & Relation Types
# -----------------------------------------------------------------------------

@router.get(
    "/universes/{universe_id}/entity-types", response_model=list[EntityTypeResponse]
)
def get_entity_types(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> list[EntityTypeResponse]:
    user = get_current_account(request, db)
    results = list_entity_types(db, universe_id, user)
    return [EntityTypeResponse.model_validate(et) for et in results]


@router.post(
    "/universes/{universe_id}/entity-types",
    response_model=EntityTypeResponse,
    status_code=201,
)
def create_new_entity_type(
    universe_id: uuid.UUID,
    payload: EntityTypeCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EntityTypeResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    created = create_entity_type(
        db, universe_id, user, payload, request_id=request_id
    )
    return EntityTypeResponse.model_validate(created)


@router.patch(
    "/universes/{universe_id}/entity-types/{type_id}",
    response_model=EntityTypeResponse,
)
def update_existing_entity_type(
    universe_id: uuid.UUID,
    type_id: uuid.UUID,
    payload: EntityTypeUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> EntityTypeResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    updated = update_entity_type(
        db, universe_id, type_id, user, payload, request_id=request_id
    )
    return EntityTypeResponse.model_validate(updated)


@router.get(
    "/universes/{universe_id}/relation-types",
    response_model=list[RelationTypeResponse],
)
def get_relation_types(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> list[RelationTypeResponse]:
    user = get_current_account(request, db)
    results = list_relation_types(db, universe_id, user)
    return [RelationTypeResponse.model_validate(rt) for rt in results]


@router.post(
    "/universes/{universe_id}/relation-types",
    response_model=RelationTypeResponse,
    status_code=201,
)
def create_new_relation_type(
    universe_id: uuid.UUID,
    payload: RelationTypeCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> RelationTypeResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    created = create_relation_type(
        db, universe_id, user, payload, request_id=request_id
    )
    return RelationTypeResponse.model_validate(created)


# -----------------------------------------------------------------------------
# Entities CRUD
# -----------------------------------------------------------------------------

@router.get("/universes/{universe_id}/entities", response_model=EntityListResponse)
def get_entities(
    universe_id: uuid.UUID,
    request: Request,
    type: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> EntityListResponse:
    user = get_current_account(request, db)
    items, total = list_entities(
        db,
        universe_id,
        user,
        type_key=type,
        status=status,
        tag=tag,
        search=q,
        limit=limit,
        offset=offset,
    )
    return EntityListResponse(
        items=[EntityResponse.model_validate(e) for e in items],
        total=total,
    )


@router.post(
    "/universes/{universe_id}/entities",
    response_model=EntityResponse,
    status_code=201,
)
def create_new_entity(
    universe_id: uuid.UUID,
    payload: EntityCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EntityResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    created = create_entity(db, universe_id, user, payload, request_id=request_id)
    return EntityResponse.model_validate(created)


@router.get(
    "/universes/{universe_id}/entities/{entity_id}", response_model=EntityResponse
)
def get_entity(
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> EntityResponse:
    user = get_current_account(request, db)
    entity = get_entity_details(db, universe_id, entity_id, user)
    return EntityResponse.model_validate(entity)


@router.patch(
    "/universes/{universe_id}/entities/{entity_id}", response_model=EntityResponse
)
def modify_entity(
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: EntityUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> EntityResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    updated = update_entity(
        db, universe_id, entity_id, user, payload, request_id=request_id
    )
    return EntityResponse.model_validate(updated)


@router.delete("/universes/{universe_id}/entities/{entity_id}", status_code=204)
def remove_entity(
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    delete_entity(db, universe_id, entity_id, user, request_id=request_id)
    return Response(status_code=204)


@router.post(
    "/universes/{universe_id}/entities/{entity_id}/restore",
    response_model=EntityResponse,
)
def restore_deleted_entity(
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> EntityResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    restored = restore_entity(
        db, universe_id, entity_id, user, request_id=request_id
    )
    return EntityResponse.model_validate(restored)


# -----------------------------------------------------------------------------
# Relations
# -----------------------------------------------------------------------------

@router.get(
    "/universes/{universe_id}/entities/{entity_id}/relations",
    response_model=list[EntityRelationResponse],
)
def get_entity_relations(
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> list[EntityRelationResponse]:
    user = get_current_account(request, db)
    results = list_entity_relations(db, universe_id, entity_id, user)
    return [EntityRelationResponse.model_validate(r) for r in results]


@router.post(
    "/universes/{universe_id}/relations",
    response_model=EntityRelationResponse,
    status_code=201,
)
def create_entity_relation(
    universe_id: uuid.UUID,
    payload: EntityRelationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EntityRelationResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    created = create_relation(
        db,
        universe_id,
        user,
        payload.source_entity_id,
        payload.relation_type_key,
        payload.target_entity_id,
        attributes=payload.attributes_json,
        request_id=request_id,
    )
    return EntityRelationResponse.model_validate(created)


@router.delete(
    "/universes/{universe_id}/relations/{relation_id}", status_code=204
)
def remove_relation(
    universe_id: uuid.UUID,
    relation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    delete_relation(db, universe_id, relation_id, user, request_id=request_id)
    return Response(status_code=204)


# -----------------------------------------------------------------------------
# Nexus Graph
# -----------------------------------------------------------------------------

@router.get("/universes/{universe_id}/graph", response_model=GraphResponse)
def get_nexus_graph(
    universe_id: uuid.UUID,
    request: Request,
    focus_entity_id: uuid.UUID | None = None,
    depth: int = Query(default=1, ge=1, le=3),
    type_keys: Annotated[list[str] | None, Query()] = None,
    entity_type_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    relation_type_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    limit: int = Query(default=150, ge=10, le=500),
    db: Session = Depends(get_db),
) -> GraphResponse:
    user = get_current_account(request, db)
    data = query_graph(
        db,
        universe_id,
        user,
        focus_entity_id=focus_entity_id,
        depth=depth,
        type_keys=type_keys,
        entity_type_ids=entity_type_ids,
        relation_type_ids=relation_type_ids,
        limit=limit,
    )
    return GraphResponse.model_validate(data)
