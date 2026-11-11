from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.database import get_db
from backend.core.models import User
from backend.modules.identity.schemas import (
    AccountResponse,
    LoginInput,
    RegistrationInput,
)
from backend.modules.identity.service import (
    get_current_account,
    login_account,
    register_account,
    revoke_current_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/register", response_model=AccountResponse, status_code=201)
def register(
    payload: RegistrationInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccountResponse:
    account = register_account(
        request,
        response,
        db,
        settings,
        email=str(payload.email),
        password=payload.password,
        display_name=payload.display_name,
    )
    return AccountResponse.model_validate(account)


@router.post("/login", response_model=AccountResponse)
def login(
    payload: LoginInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccountResponse:
    account = login_account(
        request,
        response,
        db,
        settings,
        email=str(payload.email),
        password=payload.password,
    )
    return AccountResponse.model_validate(account)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    revoke_current_session(request, response, db, settings)
    response.status_code = 204
    response.body = b""
    return response


@router.get("/me", response_model=AccountResponse)
def current_account(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    return get_current_account(request, db)
