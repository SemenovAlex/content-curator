from datetime import datetime, timezone
from pathlib import Path

import pytest

from curator.finalize import IncompleteAnalysisError, finalize_day
from curator.models import AnalysisRecord, IngestItem, IngestManifest
from curator.storage import load_history_range, save_analysis, save_manifest
from curator.utils import utcnow


def item(source_id: str, content_id: str) -> IngestItem:
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    return IngestItem(
        date="2026-09-10", source_id=source_id, content_id=content_id, title="Title", source_name=source_id,
        source_role="research", url="https://example.com/a", canonical_url="https://example.com/a/",
        discovered_from="https://example.com/", published_at=now, discovered_at=now,
        extraction_status="ok", extraction_method="http+trafilatura",
    )


def analysis(content_id: str) -> AnalysisRecord:
    return AnalysisRecord(
        date="2026-09-10", content_id=content_id, category="summary_enough", score=7,
        reason="Relevant", summary="Summary", topics=["agents"], analyzed_at=utcnow(),
    )


def test_finalize_requires_each_unique_content_id(tmp_path: Path) -> None:
    save_manifest(tmp_path, IngestManifest(
        date="2026-09-10", timezone="Europe/Moscow", generated_at=utcnow(), source_ids=["a", "b"],
        items=[item("a", "article:one"), item("b", "article:one"), item("b", "article:two")],
    ))
    save_analysis(tmp_path, analysis("article:one"))
    with pytest.raises(IncompleteAnalysisError):
        finalize_day(tmp_path, "2026-09-10")
    save_analysis(tmp_path, analysis("article:two"))
    finalized = finalize_day(tmp_path, "2026-09-10")
    assert finalized.total_unique == 2
    assert finalized.source_attribution["article:one"] == ["a", "b"]
    finalize_day(tmp_path, "2026-09-10")
    rows = load_history_range(tmp_path, datetime(2026, 9, 10).date(), datetime(2026, 9, 10).date())
    assert len(rows) == 2


def test_refinalize_replaces_removed_content_in_history(tmp_path: Path) -> None:
    save_manifest(tmp_path, IngestManifest(
        date="2026-09-10", timezone="Europe/Moscow", generated_at=utcnow(), source_ids=["a"], items=[item("a", "article:old")],
    ))
    save_analysis(tmp_path, analysis("article:old"))
    finalize_day(tmp_path, "2026-09-10")
    save_manifest(tmp_path, IngestManifest(
        date="2026-09-10", timezone="Europe/Moscow", generated_at=utcnow(), source_ids=["a"], items=[item("a", "article:new")],
    ))
    save_analysis(tmp_path, analysis("article:new"))
    finalize_day(tmp_path, "2026-09-10")
    rows = load_history_range(tmp_path, datetime(2026, 9, 10).date(), datetime(2026, 9, 10).date())
    assert {row["content_id"] for row in rows} == {"article:new"}
