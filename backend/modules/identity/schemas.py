from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

DisplayName = Annotated[
    str, StringConstraints(min_length=1, max_length=80, strip_whitespace=True)
]


class RegistrationInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: DisplayName


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    created_at: datetime
