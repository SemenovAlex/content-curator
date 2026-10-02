from pathlib import Path

import yaml

from curator.config import ARTICLE_ROLES, article_sources, load_config

ROOT = Path(__file__).parents[1]


def test_article_sources_are_dynamic(tmp_path: Path) -> None:
    original = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(yaml.safe_dump(original, allow_unicode=True, sort_keys=False), encoding="utf-8")
    expected = sum(1 for row in original["sources"] if row.get("type") == "web" and row.get("content_role") in ARTICLE_ROLES)
    assert len(article_sources(load_config(config_path))) == expected
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw["sources"].append({
        "id": "extra_web_source", "name": "Extra", "type": "web", "url": "https://example.com/articles",
        "content_role": "engineering", "discovery": {"scope": "exact_page", "renderer": "http"},
    })
    config_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert len(article_sources(load_config(config_path))) == expected + 1


def test_non_article_types_validate_but_are_excluded() -> None:
    config = load_config(ROOT / "sources.yaml")
    assert {source.type.value for source in config.sources} >= {"web", "telegram", "podcast"}
    assert all(source.type.value == "web" for source in article_sources(config))
