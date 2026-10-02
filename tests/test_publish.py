from datetime import datetime, timezone
from pathlib import Path

import pytest

from curator.models import AnalysisRecord, IngestItem, IngestManifest
from curator.publish import publish_digest
from curator.storage import save_analysis, save_manifest
from curator.utils import utcnow


def prepare(root: Path) -> None:
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    save_manifest(root, IngestManifest(
        date="2026-09-10", timezone="Europe/Moscow", generated_at=utcnow(), source_ids=["a"],
        items=[IngestItem(
            date="2026-09-10", source_id="a", content_id="article:one", title="Title", source_name="A",
            source_role="research", url="https://example.com/a", canonical_url="https://example.com/a/",
            discovered_from="https://example.com/", published_at=now, discovered_at=now,
            extraction_status="ok", extraction_method="test",
        )],
    ))
    save_analysis(root, AnalysisRecord(
        date="2026-09-10", content_id="article:one", category="skip", score=2,
        reason="low value", summary="", analyzed_at=utcnow(),
    ))


def digest_text() -> str:
    return "---\ndate: 2026-09-10\ngenerated: 2026-09-11T06:00:00+03:00\ntags:\n  - content-curator\n  - ai-ml\n---\n\n# AI/ML digest — 2026-09-10\n"


def test_publish_writes_only_expected_obsidian_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "data"
    vault = tmp_path / "vault"
    source = tmp_path / "workspace" / "digest.md"
    source.parent.mkdir()
    source.write_text(digest_text(), encoding="utf-8")
    prepare(root)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    monkeypatch.setenv("OBSIDIAN_DIGEST_DIR", "Digital Twin/90 Agent/Content Curator/Digests")
    destination = publish_digest(root, "2026-09-10", source)
    assert destination == vault / "Digital Twin/90 Agent/Content Curator/Digests/2026-09-10.md"
    assert list(vault.rglob("*.md")) == [destination]
    assert not (root / "runs/2026-09-10/digest.md").exists()


def test_publish_rejects_vault_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "data"
    source = tmp_path / "digest.md"
    source.write_text(digest_text(), encoding="utf-8")
    prepare(root)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OBSIDIAN_DIGEST_DIR", "../escape")
    with pytest.raises(ValueError, match="escapes"):
        publish_digest(root, "2026-09-10", source)
