from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.modules.chronicle.schemas import (
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    CommentUpdate,
    DocumentCreate,
    DocumentEntityLinkResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentRestoreRequest,
    DocumentRevisionListResponse,
    DocumentRevisionResponse,
    DocumentSummary,
    DocumentTreeResponse,
    DocumentUpdate,
)
from backend.modules.chronicle.service import (
    create_document,
    create_document_comment,
    delete_document,
    delete_document_comment,
    get_document_details,
    get_document_revision,
    get_document_tree,
    list_document_comments,
    list_document_links,
    list_document_revisions,
    list_documents,
    list_entity_documents,
    restore_document,
    restore_document_revision,
    update_document,
    update_document_comment,
)
from backend.modules.identity.service import get_current_account

router = APIRouter(prefix="/api/v1", tags=["chronicle"])


@router.get(
    "/universes/{universe_id}/documents",
    response_model=DocumentListResponse,
)
def get_documents(
    universe_id: uuid.UUID,
    request: Request,
    parent_id: uuid.UUID | None = None,
    root_only: bool = False,
    type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    user = get_current_account(request, db)
    items, total = list_documents(
        db,
        universe_id,
        user,
        parent_id=parent_id,
        root_only=root_only,
        document_type=type,
        status=status,
        search=q,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[DocumentSummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/universes/{universe_id}/documents",
    response_model=DocumentResponse,
    status_code=201,
)
def create_new_document(
    universe_id: uuid.UUID,
    payload: DocumentCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    created = create_document(
        db, universe_id, user, payload, request_id=request_id
    )
    return DocumentResponse.model_validate(created)


@router.get(
    "/universes/{universe_id}/documents/tree",
    response_model=DocumentTreeResponse,
)
def get_documents_tree(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> DocumentTreeResponse:
    user = get_current_account(request, db)
    items, total = get_document_tree(db, universe_id, user)
    return DocumentTreeResponse.model_validate({"items": items, "total": total})


@router.get(
    "/universes/{universe_id}/documents/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    user = get_current_account(request, db)
    document = get_document_details(db, universe_id, document_id, user)
    return DocumentResponse.model_validate(document)


@router.patch(
    "/universes/{universe_id}/documents/{document_id}",
    response_model=DocumentResponse,
)
def modify_document(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    updated = update_document(
        db, universe_id, document_id, user, payload, request_id=request_id
    )
    return DocumentResponse.model_validate(updated)


@router.delete(
    "/universes/{universe_id}/documents/{document_id}",
    status_code=204,
)
def remove_document(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    delete_document(
        db, universe_id, document_id, user, request_id=request_id
    )
    return Response(status_code=204)


@router.post(
    "/universes/{universe_id}/documents/{document_id}/restore",
    response_model=DocumentResponse,
)
def restore_deleted_document(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    restored = restore_document(
        db, universe_id, document_id, user, request_id=request_id
    )
    return DocumentResponse.model_validate(restored)


@router.get(
    "/universes/{universe_id}/documents/{document_id}/revisions",
    response_model=DocumentRevisionListResponse,
)
def get_document_revisions(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    include_content: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> DocumentRevisionListResponse:
    user = get_current_account(request, db)
    items, total = list_document_revisions(
        db,
        universe_id,
        document_id,
        user,
        include_content=include_content,
        limit=limit,
        offset=offset,
    )
    return DocumentRevisionListResponse(
        items=[DocumentRevisionResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/universes/{universe_id}/documents/{document_id}/revisions/{revision_id}",
    response_model=DocumentRevisionResponse,
)
def get_document_revision_details(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> DocumentRevisionResponse:
    user = get_current_account(request, db)
    revision = get_document_revision(
        db, universe_id, document_id, revision_id, user
    )
    return DocumentRevisionResponse.model_validate(revision)


@router.post(
    "/universes/{universe_id}/documents/{document_id}/restore/{revision_id}",
    response_model=DocumentResponse,
)
def restore_revision(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    payload: DocumentRestoreRequest | None = None,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    restored = restore_document_revision(
        db,
        universe_id,
        document_id,
        revision_id,
        user,
        payload or DocumentRestoreRequest(),
        request_id=request_id,
    )
    return DocumentResponse.model_validate(restored)


@router.get(
    "/universes/{universe_id}/documents/{document_id}/links",
    response_model=list[DocumentEntityLinkResponse],
)
def get_document_links(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> list[DocumentEntityLinkResponse]:
    user = get_current_account(request, db)
    links = list_document_links(db, universe_id, document_id, user)
    return [DocumentEntityLinkResponse.model_validate(link) for link in links]


@router.get(
    "/universes/{universe_id}/entities/{entity_id}/documents",
    response_model=DocumentListResponse,
)
def get_entity_documents(
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    user = get_current_account(request, db)
    items, total = list_entity_documents(
        db, universe_id, entity_id, user, limit=limit, offset=offset
    )
    return DocumentListResponse(
        items=[DocumentSummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# -----------------------------------------------------------------------------
# Comments
# -----------------------------------------------------------------------------

@router.get(
    "/universes/{universe_id}/documents/{document_id}/comments",
    response_model=CommentListResponse,
)
def get_document_comments(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CommentListResponse:
    user = get_current_account(request, db)
    items, total = list_document_comments(
        db, universe_id, document_id, user, limit=limit, offset=offset
    )
    return CommentListResponse(
        items=[CommentResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/universes/{universe_id}/documents/{document_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
def create_comment(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: CommentCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> CommentResponse:
    user = get_current_account(request, db)
    request_id = getattr(request.state, "request_id", None)
    created = create_document_comment(
        db, universe_id, document_id, user, payload, request_id=request_id
    )
    return CommentResponse.model_validate(created)


@router.patch(
    "/universes/{universe_id}/documents/{document_id}/comments/{comment_id}",
    response_model=CommentResponse,
)
def modify_comment(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    comment_id: uuid.UUID,
    payload: CommentUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> CommentResponse:
    user = get_current_account(request, db)
    updated = update_document_comment(
        db, universe_id, document_id, comment_id, user, payload
    )
    return CommentResponse.model_validate(updated)


@router.delete(
    "/universes/{universe_id}/documents/{document_id}/comments/{comment_id}",
    status_code=204,
)
def remove_comment(
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    comment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    delete_document_comment(
        db, universe_id, document_id, comment_id, user
    )
    return Response(status_code=204)
