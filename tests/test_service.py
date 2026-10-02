from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from curator.config import DiscoveryConfig, SourceConfig
from curator.extract import ExtractedArticle
from curator.fetch import FetchResult
from curator.models import DiscoveryCandidate
from curator.service import ingest_source
from curator.storage import load_state, save_state
from curator.utils import stable_hash


def source() -> SourceConfig:
    return SourceConfig(
        id="example", name="Example", type="web", url="https://example.com/research", content_role="research",
        discovery=DiscoveryConfig(renderer="http"),
    )


def candidate(discovered_date: str | None = None) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        source_id="example", source_name="Example", source_role="research",
        fetch_url="https://example.com/article", canonical_url="https://example.com/article/",
        discovered_from="https://example.com/research", anchor_text="Article", context_text="Article",
        context_fingerprint=stable_hash("Article"), discovered_date=discovered_date,
        discovered_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )


def patch_extract(monkeypatch: pytest.MonkeyPatch, published_at=None) -> None:
    monkeypatch.setattr("curator.service.fetch_article", lambda *a, **k: FetchResult(url="https://example.com/article", text="<html></html>", method="http"))
    monkeypatch.setattr("curator.service.extract_article", lambda *a, **k: ExtractedArticle(
        title="Article", description="", published_at=published_at, text="x" * 300, method="trafilatura",
    ))


def test_stateful_baseline_can_supply_previously_verified_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    save_state(tmp_path, "example", {"source_id": "example", "items": {"https://example.com/article/": {"published_at": "2026-09-10T10:00:00+00:00"}}})
    patch_extract(monkeypatch)
    items, errors, _ = ingest_source(source(), [candidate()], date(2026, 9, 10), "Europe/Moscow", tmp_path, stateless=False)
    assert len(items) == 1
    assert not errors
    assert load_state(tmp_path, "example")["items"]


def test_stateless_historical_run_rejects_undated_index_even_if_detail_has_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_extract(monkeypatch, datetime(2026, 9, 10, 10, tzinfo=timezone.utc))
    items, errors, _ = ingest_source(source(), [candidate()], date(2026, 9, 10), "Europe/Moscow", tmp_path, stateless=True)
    assert items == []
    assert errors == []


def test_stateless_accepts_reliably_dated_index_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_extract(monkeypatch)
    items, errors, _ = ingest_source(source(), [candidate("2026-09-10T10:00:00+00:00")], date(2026, 9, 10), "Europe/Moscow", tmp_path, stateless=True)
    assert len(items) == 1
    assert errors == []
