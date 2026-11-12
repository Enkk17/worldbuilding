from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.modules.chronos.schemas import (
    CalendarCreate,
    CalendarListResponse,
    CalendarResponse,
    CalendarUpdate,
    EraCreate,
    EraListResponse,
    EraResponse,
    EraUpdate,
    TimelineEventCreate,
    TimelineEventListResponse,
    TimelineEventResponse,
    TimelineEventUpdate,
)
from backend.modules.chronos.service import (
    create_calendar,
    create_era,
    create_event,
    delete_era,
    delete_event,
    get_calendar,
    get_event,
    list_calendars,
    list_eras,
    list_events,
    update_calendar,
    update_era,
    update_event,
)
from backend.modules.identity.service import get_current_account

router = APIRouter(prefix="/api/v1", tags=["chronos"])


@router.get("/universes/{universe_id}/calendars", response_model=CalendarListResponse)
def get_calendars(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CalendarListResponse:
    user = get_current_account(request, db)
    items, total = list_calendars(db, universe_id, user, limit, offset)
    return CalendarListResponse(items=items, total=total)


@router.post(
    "/universes/{universe_id}/calendars",
    response_model=CalendarResponse,
    status_code=201,
)
def create_new_calendar(
    universe_id: uuid.UUID,
    payload: CalendarCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> CalendarResponse:
    user = get_current_account(request, db)
    record = create_calendar(
        db,
        universe_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return CalendarResponse.model_validate(record)


@router.get(
    "/universes/{universe_id}/calendars/{calendar_id}",
    response_model=CalendarResponse,
)
def get_calendar_detail(
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> CalendarResponse:
    user = get_current_account(request, db)
    return CalendarResponse.model_validate(
        get_calendar(db, universe_id, calendar_id, user)
    )


@router.patch(
    "/universes/{universe_id}/calendars/{calendar_id}",
    response_model=CalendarResponse,
)
def update_calendar_detail(
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    payload: CalendarUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> CalendarResponse:
    user = get_current_account(request, db)
    record = update_calendar(
        db,
        universe_id,
        calendar_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return CalendarResponse.model_validate(record)


@router.get(
    "/universes/{universe_id}/calendars/{calendar_id}/eras",
    response_model=EraListResponse,
)
def get_calendar_eras(
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> EraListResponse:
    user = get_current_account(request, db)
    items, total = list_eras(db, universe_id, calendar_id, user)
    return EraListResponse(items=items, total=total)


@router.post(
    "/universes/{universe_id}/calendars/{calendar_id}/eras",
    response_model=EraResponse,
    status_code=201,
)
def create_calendar_era(
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    payload: EraCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EraResponse:
    user = get_current_account(request, db)
    record = create_era(
        db,
        universe_id,
        calendar_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return EraResponse.model_validate(record)


@router.patch(
    "/universes/{universe_id}/calendars/{calendar_id}/eras/{era_id}",
    response_model=EraResponse,
)
def update_calendar_era(
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    era_id: uuid.UUID,
    payload: EraUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> EraResponse:
    user = get_current_account(request, db)
    record = update_era(
        db,
        universe_id,
        calendar_id,
        era_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return EraResponse.model_validate(record)


@router.delete(
    "/universes/{universe_id}/calendars/{calendar_id}/eras/{era_id}",
    status_code=204,
    response_class=Response,
)
def delete_calendar_era(
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    era_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    delete_era(
        db,
        universe_id,
        calendar_id,
        era_id,
        user,
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=204)


@router.get(
    "/universes/{universe_id}/timeline-events",
    response_model=TimelineEventListResponse,
)
def get_timeline_events(
    universe_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    calendar_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TimelineEventListResponse:
    user = get_current_account(request, db)
    items, total = list_events(
        db,
        universe_id,
        user,
        calendar_id=calendar_id,
        search=q,
        limit=limit,
        offset=offset,
    )
    return TimelineEventListResponse(items=items, total=total)


@router.post(
    "/universes/{universe_id}/timeline-events",
    response_model=TimelineEventResponse,
    status_code=201,
)
def create_timeline_event(
    universe_id: uuid.UUID,
    payload: TimelineEventCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> TimelineEventResponse:
    user = get_current_account(request, db)
    record = create_event(
        db,
        universe_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return TimelineEventResponse.model_validate(record)


@router.get(
    "/universes/{universe_id}/timeline-events/{event_id}",
    response_model=TimelineEventResponse,
)
def get_timeline_event(
    universe_id: uuid.UUID,
    event_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> TimelineEventResponse:
    user = get_current_account(request, db)
    return TimelineEventResponse.model_validate(
        get_event(db, universe_id, event_id, user)
    )


@router.patch(
    "/universes/{universe_id}/timeline-events/{event_id}",
    response_model=TimelineEventResponse,
)
def update_timeline_event(
    universe_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: TimelineEventUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> TimelineEventResponse:
    user = get_current_account(request, db)
    record = update_event(
        db,
        universe_id,
        event_id,
        user,
        payload,
        request_id=getattr(request.state, "request_id", None),
    )
    return TimelineEventResponse.model_validate(record)


@router.delete(
    "/universes/{universe_id}/timeline-events/{event_id}",
    status_code=204,
    response_class=Response,
)
def delete_timeline_event(
    universe_id: uuid.UUID,
    event_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    user = get_current_account(request, db)
    delete_event(
        db,
        universe_id,
        event_id,
        user,
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=204)
