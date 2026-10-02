from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from curator.storage import load_history_range

CATEGORIES = ("must_read", "summary_enough", "skip", "unprocessed")


def compute_stats(root: Path, start: date, end: date) -> dict[str, Any]:
    rows = load_history_range(root, start, end)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {category: 0 for category in CATEGORIES})
    for row in rows:
        category = row.get("category")
        if category not in CATEGORIES:
            continue
        for source_id in row.get("source_ids", []):
            counts[source_id][category] += 1
    sources: dict[str, Any] = {}
    for source_id, source_counts in sorted(counts.items()):
        processed = source_counts["must_read"] + source_counts["summary_enough"] + source_counts["skip"]
        useful = source_counts["must_read"] + source_counts["summary_enough"]
        sources[source_id] = {
            **source_counts,
            "processed": processed,
            "useful_rate": useful / processed if processed else 0.0,
            "must_read_rate": source_counts["must_read"] / processed if processed else 0.0,
        }
    return {"from": start.isoformat(), "to": end.isoformat(), "sources": sources}


def render_chart(stats: dict[str, Any], path: Path) -> None:
    source_ids = list(stats["sources"])
    values = {category: [stats["sources"][source][category] for source in source_ids] for category in CATEGORIES}
    fig, ax = plt.subplots(figsize=(max(8, len(source_ids) * 0.7), 5))
    bottoms = [0] * len(source_ids)
    for category in CATEGORIES:
        ax.bar(source_ids, values[category], bottom=bottoms, label=category)
        bottoms = [a + b for a, b in zip(bottoms, values[category], strict=True)]
    ax.set_xlabel("Источник")
    ax.set_ylabel("Количество материалов")
    ax.tick_params(axis="x", rotation=60)
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
