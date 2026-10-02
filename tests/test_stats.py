from datetime import date
from pathlib import Path

from curator.statistics import compute_stats
from curator.storage import _rewrite_jsonl


def test_stats_rates_use_processed_denominator(tmp_path: Path) -> None:
    _rewrite_jsonl(tmp_path / "history/2026-09.jsonl", [
        {"date": "2026-09-10", "content_id": "1", "category": "must_read", "source_ids": ["a"]},
        {"date": "2026-09-10", "content_id": "2", "category": "summary_enough", "source_ids": ["a"]},
        {"date": "2026-09-10", "content_id": "3", "category": "skip", "source_ids": ["a"]},
        {"date": "2026-09-10", "content_id": "4", "category": "unprocessed", "source_ids": ["a"]},
    ])
    result = compute_stats(tmp_path, date(2026, 9, 1), date(2026, 9, 30))["sources"]["a"]
    assert result["processed"] == 3
    assert result["useful_rate"] == 2 / 3
    assert result["must_read_rate"] == 1 / 3
