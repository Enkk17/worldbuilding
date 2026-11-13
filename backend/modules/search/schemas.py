from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    id: str
    kind: Literal["entity", "document", "timeline_event"]
    title: str
    summary: str
    snippet: str
    highlight_start: int
    highlight_end: int
    href: str
    updated_at: str


class SearchResponse(BaseModel):
    query: str
    items: list[SearchResult]
    total: int
    limit: int
    offset: int
