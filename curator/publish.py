from __future__ import annotations

import os
from pathlib import Path

from curator.finalize import IncompleteAnalysisError, finalize_day
from curator.storage import load_analysis, load_manifest
from curator.utils import atomic_write_text


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_complete(root: Path, day: str) -> None:
    manifest = load_manifest(root, day)
    if manifest is None:
        raise FileNotFoundError(f"ingest manifest not found for {day}")
    analyzed = {record.content_id for record in load_analysis(root, day)}
    required = {item.content_id for item in manifest.items}
    missing = sorted(required - analyzed)
    if missing:
        raise IncompleteAnalysisError("refusing to publish incomplete digest; missing analysis for: " + ", ".join(missing))


def publish_digest(root: Path, day: str, input_path: Path) -> Path:
    validate_complete(root, day)
    finalize_day(root, day)
    vault_raw = os.getenv("OBSIDIAN_VAULT_PATH")
    digest_dir_raw = os.getenv("OBSIDIAN_DIGEST_DIR")
    if not vault_raw or not digest_dir_raw:
        raise RuntimeError("OBSIDIAN_VAULT_PATH and OBSIDIAN_DIGEST_DIR must be set")
    vault = Path(vault_raw).expanduser().resolve()
    digest_dir = (vault / digest_dir_raw).resolve()
    if not _inside(digest_dir, vault):
        raise ValueError("OBSIDIAN_DIGEST_DIR escapes OBSIDIAN_VAULT_PATH")
    source = input_path.expanduser().resolve()
    if source == (root / "runs" / day / "digest.md").resolve():
        raise ValueError("data/runs/YYYY-MM-DD/digest.md is forbidden by the project contract")
    content = source.read_text(encoding="utf-8")
    if f"date: {day}" not in content or f"# AI/ML digest — {day}" not in content:
        raise ValueError("digest date/frontmatter does not match --date")
    destination = (digest_dir / f"{day}.md").resolve()
    if not _inside(destination, vault):
        raise ValueError("digest destination escapes OBSIDIAN_VAULT_PATH")
    atomic_write_text(destination, content.rstrip() + "\n")
    return destination
