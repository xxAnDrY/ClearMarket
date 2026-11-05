"""Contratto JSON dell'API."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SourceOut(BaseModel):
    slug: str
    name: str


class SentimentOut(BaseModel):
    label: Literal["positive", "neutral", "negative"]
    score: float


class ArticleOut(BaseModel):
    id: UUID
    title: str
    summary: str
    source: SourceOut
    source_url: str
    translated: bool
    published_at: datetime
    category: str
    related_tickers: list[str]
    sentiment: SentimentOut


class PageInfo(BaseModel):
    next_cursor: str | None
    has_more: bool
    limit: int


class FeedResponse(BaseModel):
    data: list[ArticleOut]
    page_info: PageInfo


class EconomicEventOut(BaseModel):
    id: UUID
    title: str
    country: str
    starts_at: datetime
    impact: Literal["low", "medium", "high", "holiday"]
    forecast: str | None
    previous: str | None
    actual: str | None


class CalendarResponse(BaseModel):
    date: str
    timezone: str
    data: list[EconomicEventOut]


class CategoryOut(BaseModel):
    slug: str
    label: str


class Watchlist(BaseModel):
    tickers: list[str] = Field(default_factory=list, max_length=100)
    categories: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tickers")
    @classmethod
    def _normalize_tickers(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))
        for ticker in cleaned:
            if len(ticker) > 15 or not all(c.isalnum() or c in ".-" for c in ticker):
                raise ValueError(f"invalid ticker: {ticker}")
        return cleaned
