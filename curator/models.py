from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_name: str
    source_role: str
    fetch_url: str
    canonical_url: str
    discovered_from: str
    anchor_text: str = ""
    context_text: str = ""
    context_fingerprint: str
    discovered_date: str | None = None
    discovered_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    source_id: str
    content_id: str
    title: str
    content_type: Literal["article"] = "article"
    source_name: str
    source_role: str
    url: str
    canonical_url: str
    discovered_from: str
    published_at: datetime | None = None
    discovered_at: datetime
    description: str = ""
    extraction_status: Literal["ok", "error", "rejected"]
    extraction_method: str
    text_file: str | None = None
    excerpt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestError(BaseModel):
    source_id: str
    stage: str
    url: str | None = None
    error: str


class IngestManifest(BaseModel):
    schema_version: int = 1
    kind: Literal["article_ingest"] = "article_ingest"
    date: str
    timezone: str
    generated_at: datetime
    source_ids: list[str]
    items: list[IngestItem]
    errors: list[IngestError] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


AnalysisCategory = Literal["must_read", "summary_enough", "skip", "unprocessed"]


class AnalysisRecord(BaseModel):
    schema_version: int = 1
    date: str
    content_id: str
    category: AnalysisCategory
    score: int = Field(ge=1, le=10)
    reason: str
    summary: str
    topics: list[str] = Field(default_factory=list)
    language: str | None = None
    reading_minutes: int | None = Field(default=None, ge=0)
    insights: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    takeaways: list[str] = Field(default_factory=list)
    verdict: str | None = None
    analyzed_at: datetime


class FinalizedDay(BaseModel):
    schema_version: int = 1
    date: str
    finalized_at: datetime
    total_unique: int
    category_counts: dict[str, int]
    analysis: list[AnalysisRecord]
    source_attribution: dict[str, list[str]]
