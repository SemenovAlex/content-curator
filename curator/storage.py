from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from curator.models import AnalysisRecord, FinalizedDay, IngestManifest
from curator.utils import atomic_write_text, json_dumps, utcnow


def data_dir(config_path: Path | None = None) -> Path:
    if env := os.getenv("CURATOR_DATA_DIR"):
        return Path(env).expanduser().resolve()
    if config_path:
        return (config_path.resolve().parent / "data").resolve()
    return (Path.cwd() / "data").resolve()


def run_dir(root: Path, day: str) -> Path:
    return root / "runs" / day


def manifest_path(root: Path, day: str) -> Path:
    return run_dir(root, day) / "article_ingest.json"


def load_manifest(root: Path, day: str) -> IngestManifest | None:
    path = manifest_path(root, day)
    if not path.exists():
        return None
    return IngestManifest.model_validate_json(path.read_text(encoding="utf-8"))


def save_manifest(root: Path, manifest: IngestManifest) -> None:
    atomic_write_text(manifest_path(root, manifest.date), json_dumps(manifest.model_dump(mode="json")) + "\n")


def _rewrite_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows)
    atomic_write_text(path, content)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def replace_jsonl_slice(path: Path, key: str, values: set[str], new_rows: list[dict[str, Any]]) -> None:
    rows = [row for row in read_jsonl(path) if str(row.get(key)) not in values]
    rows.extend(new_rows)
    _rewrite_jsonl(path, rows)


def content_paths(root: Path, content_id: str, published_day: str) -> tuple[Path, Path, str, str]:
    month = published_day[:7]
    suffix = content_id.split(":", 1)[-1]
    base = root / "content" / month / suffix
    txt = base.with_suffix(".txt")
    metadata = base.with_suffix(".json")
    return txt, metadata, str(txt.relative_to(root)), str(metadata.relative_to(root))


def save_content(root: Path, content_id: str, published_day: str, text: str, metadata: dict[str, Any]) -> str:
    txt, meta, txt_rel, _ = content_paths(root, content_id, published_day)
    atomic_write_text(txt, text.rstrip() + "\n")
    atomic_write_text(meta, json_dumps(metadata) + "\n")
    return txt_rel


def read_content(root: Path, content_id: str) -> tuple[dict[str, Any], str]:
    suffix = content_id.split(":", 1)[-1]
    matches = list((root / "content").glob(f"*/{suffix}.json"))
    if not matches:
        raise FileNotFoundError(f"content not found: {content_id}")
    metadata_path = sorted(matches)[-1]
    txt_path = metadata_path.with_suffix(".txt")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    text = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""
    return metadata, text


def save_analysis(root: Path, record: AnalysisRecord) -> None:
    path = run_dir(root, record.date) / "analysis.jsonl"
    rows = [row for row in read_jsonl(path) if row.get("content_id") != record.content_id]
    rows.append(record.model_dump(mode="json"))
    rows.sort(key=lambda row: row["content_id"])
    _rewrite_jsonl(path, rows)


def load_analysis(root: Path, day: str) -> list[AnalysisRecord]:
    return [AnalysisRecord.model_validate(row) for row in read_jsonl(run_dir(root, day) / "analysis.jsonl")]


def save_finalized(root: Path, finalized: FinalizedDay) -> None:
    atomic_write_text(
        run_dir(root, finalized.date) / "finalized.json",
        json_dumps(finalized.model_dump(mode="json")) + "\n",
    )


def upsert_history(root: Path, finalized: FinalizedDay) -> None:
    path = root / "history" / f"{finalized.date[:7]}.jsonl"
    # Finalized day is authoritative: replace the whole day slice, including items removed by re-ingest.
    rows = [row for row in read_jsonl(path) if row.get("date") != finalized.date]
    by_id = {record.content_id: record for record in finalized.analysis}
    for content_id, sources in finalized.source_attribution.items():
        row = by_id[content_id].model_dump(mode="json")
        row["source_ids"] = sources
        rows.append(row)
    rows.sort(key=lambda row: (row.get("date", ""), row.get("content_id", "")))
    _rewrite_jsonl(path, rows)


def load_history_range(root: Path, start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    month = date(start.year, start.month, 1)
    while month <= end:
        for row in read_jsonl(root / "history" / f"{month:%Y-%m}.jsonl"):
            row_day = date.fromisoformat(row["date"])
            if start <= row_day <= end:
                rows.append(row)
        month = date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)
    return rows


def load_state(root: Path, source_id: str) -> dict[str, Any]:
    path = root / "state" / f"{source_id}.json"
    if not path.exists():
        return {"source_id": source_id, "items": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(root: Path, source_id: str, state: dict[str, Any]) -> None:
    atomic_write_text(root / "state" / f"{source_id}.json", json_dumps(state) + "\n")


def cleanup(root: Path, raw_days: int = 30, content_days: int = 90, max_storage_gb: float = 5.0) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    deleted: list[str] = []
    for folder, age_days in ((root / "raw", raw_days), (root / "content", content_days)):
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            if folder.name == "content" and path.suffix == ".json":
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if now - mtime > timedelta(days=age_days):
                deleted.append(str(path))
                path.unlink(missing_ok=True)
    total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    budget = int(max_storage_gb * 1024**3)
    candidates = sorted(
        [p for p in root.rglob("*") if p.is_file() and "history" not in p.parts],
        key=lambda p: p.stat().st_mtime,
    )
    for path in candidates:
        if total <= budget:
            break
        if path.suffix not in {".txt", ".html"}:
            continue
        size = path.stat().st_size
        path.unlink(missing_ok=True)
        deleted.append(str(path))
        total -= size
    return {"deleted": deleted, "bytes_after": total, "cleaned_at": utcnow().isoformat()}
