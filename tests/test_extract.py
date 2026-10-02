from pathlib import Path

from curator.extract import extract_article

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_prefers_real_metadata_title_and_detail_date() -> None:
    article = extract_article((FIXTURES / "article.html").read_text(encoding="utf-8"), "https://example.com/article", fallback_title="Research")
    assert article.title == "Actual article title"
    assert article.published_at.isoformat().startswith("2026-09-10")
    assert article.description == "Short metadata description"
    assert len(article.text) > 200


def test_generic_title_falls_back_to_card_title() -> None:
    html = "<html><head><meta property='og:title' content='Research'></head><body><h1>News</h1><main><p>" + ("Useful text. " * 40) + "</p></main></body></html>"
    assert extract_article(html, "https://example.com/a", fallback_title="Specific useful title").title == "Specific useful title"
