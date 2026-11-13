from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.modules.identity.service import get_current_account
from backend.modules.search.schemas import SearchResponse, SearchResult
from backend.modules.search.service import MAX_RESULT_LIMIT, search_universe

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/universes/{universe_id}/search", response_model=SearchResponse)
def search(
    universe_id: uuid.UUID,
    request: Request,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    types: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_RESULT_LIMIT)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> SearchResponse:
    user = get_current_account(request, db)
    items, total = search_universe(
        db,
        universe_id,
        user,
        query=q,
        kinds=types,
        limit=limit,
        offset=offset,
    )
    return SearchResponse(
        query=q,
        items=[SearchResult.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
