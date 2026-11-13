from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CalendarMonth(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    days: int = Field(ge=1, le=1000)


class LeapRule(BaseModel):
    every_years: int = Field(ge=1, le=1_000_000)
    year_offset: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    month: int = Field(ge=1, le=36)
    extra_days: int = Field(default=1, ge=1, le=1000)


class CalendarConfiguration(BaseModel):
    months: list[CalendarMonth] = Field(min_length=1, max_length=36)
    weekdays: list[str] = Field(default_factory=list, max_length=32)
    epoch_offset: int = Field(default=0, ge=-1_000_000_000, le=1_000_000_000)
    leap_rules: list[LeapRule] = Field(default_factory=list, max_length=36)

    @model_validator(mode="after")
    def validate_names(self):
        month_names = [month.name.strip().casefold() for month in self.months]
        if any(not name for name in month_names) or len(set(month_names)) != len(month_names):
            raise ValueError("Month names must be non-empty and unique.")
        weekday_names = [name.strip().casefold() for name in self.weekdays]
        if any(not name for name in weekday_names) or len(set(weekday_names)) != len(weekday_names):
            raise ValueError("Weekday names must be non-empty and unique.")
        rule_keys = set()
        for rule in self.leap_rules:
            if rule.month > len(self.months):
                raise ValueError("A leap rule must target a month defined by this calendar.")
            key = (rule.every_years, rule.year_offset % rule.every_years, rule.month)
            if key in rule_keys:
                raise ValueError("Leap rules for the same cycle and month must be combined.")
            rule_keys.add(key)
        return self


class CalendarDate(BaseModel):
    year: int = Field(ge=-1_000_000, le=1_000_000)
    month: int | None = Field(default=None, ge=1, le=36)
    day: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_parts(self):
        if self.day is not None and self.month is None:
            raise ValueError("A day requires a month.")
        return self


class CalendarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    config_json: CalendarConfiguration


class CalendarUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    config_json: CalendarConfiguration | None = None
    expected_version: int = Field(ge=1)


class CalendarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    name: str
    description: str | None
    config_json: dict[str, Any]
    created_by: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime


class CalendarListResponse(BaseModel):
    items: list[CalendarResponse]
    total: int


class EraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    start_day_index: int = Field(ge=-100_000_000_000, le=100_000_000_000)
    description: str | None = Field(default=None, max_length=1000)


class EraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    start_day_index: int | None = Field(default=None, ge=-100_000_000_000, le=100_000_000_000)
    description: str | None = Field(default=None, max_length=1000)
    expected_version: int = Field(ge=1)


class EraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    calendar_id: uuid.UUID
    name: str
    start_day_index: int
    description: str | None
    version: int


class EraListResponse(BaseModel):
    items: list[EraResponse]
    total: int


class TimelineEventCreate(BaseModel):
    calendar_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    start_date_json: CalendarDate
    end_date_json: CalendarDate | None = None
    date_precision: Literal["day", "month", "year", "range", "approximate"] = "day"
    uncertainty_json: dict[str, int] | None = None
    linked_entity_id: uuid.UUID | None = None
    linked_document_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_uncertainty(self):
        if self.uncertainty_json is not None:
            allowed = {"before_days", "after_days"}
            if set(self.uncertainty_json) - allowed:
                raise ValueError("Uncertainty supports before_days and after_days only.")
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10_000_000
                for value in self.uncertainty_json.values()
            ):
                raise ValueError("Uncertainty day counts must be non-negative integers.")
        if self.date_precision == "approximate" and self.uncertainty_json is None:
            raise ValueError("Approximate dates need an uncertainty window.")
        if self.date_precision == "range" and self.end_date_json is None:
            raise ValueError("Range dates need an end date.")
        if self.date_precision != "range" and self.end_date_json is not None:
            raise ValueError("Only range dates may include an end date.")
        return self


class TimelineEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    start_date_json: CalendarDate | None = None
    end_date_json: CalendarDate | None = None
    date_precision: Literal["day", "month", "year", "range", "approximate"] | None = None
    uncertainty_json: dict[str, int] | None = None
    linked_entity_id: uuid.UUID | None = None
    linked_document_id: uuid.UUID | None = None
    expected_version: int = Field(ge=1)


class TimelineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    universe_id: uuid.UUID
    calendar_id: uuid.UUID
    title: str
    description: str | None
    start_date_json: dict[str, Any]
    end_date_json: dict[str, Any] | None
    start_day_index: int
    end_day_index: int | None
    date_precision: str
    uncertainty_json: dict[str, Any] | None
    linked_entity_id: uuid.UUID | None
    linked_document_id: uuid.UUID | None
    created_by: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime


class TimelineEventListResponse(BaseModel):
    items: list[TimelineEventResponse]
    total: int
