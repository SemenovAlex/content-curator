from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from curator.config import CuratorConfig, DiscoveryConfig, SourceConfig
from curator.models import IngestItem
from curator.service import ingest_articles
from curator.storage import load_manifest


def make_source(source_id: str) -> SourceConfig:
    return SourceConfig(
        id=source_id, name=source_id.upper(), type="web", url=f"https://example.com/{source_id}", content_role="research",
        discovery=DiscoveryConfig(renderer="http"),
    )


def make_item(source_id: str, suffix: str) -> IngestItem:
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    return IngestItem(
        date="2026-09-10", source_id=source_id, content_id=f"article:{suffix}", title=f"Title {suffix}",
        source_name=source_id.upper(), source_role="research", url=f"https://example.com/{suffix}",
        canonical_url=f"https://example.com/{suffix}/", discovered_from=f"https://example.com/{source_id}",
        published_at=now, discovered_at=now, extraction_status="ok", extraction_method="test",
    )


def test_stdout_slice_requested_only_saved_manifest_cumulative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = make_source("source_a"), make_source("source_b")
    config = CuratorConfig(sources=[a, b])
    monkeypatch.setattr("curator.service.discover_many", lambda sources, workers: ([], []))
    versions = {"source_a": "a1", "source_b": "b1"}
    monkeypatch.setattr("curator.service.ingest_source", lambda source, *args, **kwargs: ([make_item(source.id, versions[source.id])], [], []))
    first = ingest_articles(config, [a], date(2026, 9, 10), "Europe/Moscow", tmp_path, workers=1)
    second = ingest_articles(config, [b], date(2026, 9, 10), "Europe/Moscow", tmp_path, workers=1)
    assert first.source_ids == ["source_a"]
    assert second.source_ids == ["source_b"]
    cumulative = load_manifest(tmp_path, "2026-09-10")
    assert {item.content_id for item in cumulative.items} == {"article:a1", "article:b1"}
    versions["source_a"] = "a2"
    ingest_articles(config, [a], date(2026, 9, 10), "Europe/Moscow", tmp_path, workers=1)
    cumulative = load_manifest(tmp_path, "2026-09-10")
    assert {item.content_id for item in cumulative.items} == {"article:a2", "article:b1"}
