from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceType(StrEnum):
    WEB = "web"
    TELEGRAM = "telegram"
    PODCAST = "podcast"


ARTICLE_ROLES = {
    "newsletter",
    "research",
    "technical_newsletter",
    "optimization_engineering",
    "primary_research",
    "primary_research_engineering",
    "technical_research_ecosystem",
    "academic_journal",
    "research_papers",
    "engineering",
    "company_news",
}


class DiscoveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["exact_page"] = "exact_page"
    renderer: Literal["http", "browser", "auto"] = "auto"
    include_path_regexes: list[str] = Field(default_factory=list)
    exclude_path_regexes: list[str] = Field(default_factory=list)
    allowlist_sitemaps: list[str] = Field(default_factory=list)
    mode: Literal["links", "page_snapshot", "rss"] = "links"


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: SourceType
    url: str
    content_role: str
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789_"
        if not value or any(ch not in allowed for ch in value):
            raise ValueError("source id must use lowercase letters, digits and underscores")
        return value

    @property
    def is_article_source(self) -> bool:
        return self.type == SourceType.WEB and self.content_role in ARTICLE_ROLES


class RetentionConfig(BaseModel):
    raw_retention_days: int = 30
    full_content_retention_days: int = 90
    history_retention_days: int | None = None
    max_storage_gb: float = 5.0


class CuratorConfig(BaseModel):
    sources: list[SourceConfig]
    retention: RetentionConfig = Field(default_factory=RetentionConfig)


def load_config(path: Path) -> CuratorConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return CuratorConfig(sources=raw)
    if isinstance(raw, dict) and "sources" in raw:
        return CuratorConfig.model_validate(raw)
    raise ValueError("sources.yaml must contain a list or a mapping with a 'sources' list")


def article_sources(config: CuratorConfig) -> list[SourceConfig]:
    return [source for source in config.sources if source.is_article_source]
