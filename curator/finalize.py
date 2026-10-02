from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from curator.models import FinalizedDay
from curator.storage import load_analysis, load_manifest, save_finalized, upsert_history
from curator.utils import utcnow


class IncompleteAnalysisError(RuntimeError):
    pass


def finalize_day(root: Path, day: str) -> FinalizedDay:
    manifest = load_manifest(root, day)
    if manifest is None:
        raise FileNotFoundError(f"ingest manifest not found for {day}")
    analyses = load_analysis(root, day)
    by_id = {record.content_id: record for record in analyses}
    source_attribution: dict[str, set[str]] = defaultdict(set)
    for item in manifest.items:
        source_attribution[item.content_id].add(item.source_id)
    missing = sorted(content_id for content_id in source_attribution if content_id not in by_id)
    if missing:
        raise IncompleteAnalysisError("analysis incomplete; missing content ids: " + ", ".join(missing))
    final_analysis = [by_id[content_id] for content_id in sorted(source_attribution)]
    counts = Counter(record.category for record in final_analysis)
    for category in ("must_read", "summary_enough", "skip", "unprocessed"):
        counts.setdefault(category, 0)
    finalized = FinalizedDay(
        date=day,
        finalized_at=utcnow(),
        total_unique=len(final_analysis),
        category_counts=dict(counts),
        analysis=final_analysis,
        source_attribution={key: sorted(value) for key, value in source_attribution.items()},
    )
    save_finalized(root, finalized)
    upsert_history(root, finalized)
    return finalized
