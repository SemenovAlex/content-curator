from pathlib import Path
import warnings

from bs4 import XMLParsedAsHTMLWarning

from curator.config import DiscoveryConfig, SourceConfig
from curator.discover import discover_from_feed, discover_from_html
from curator.utils import canonicalize_url

FIXTURES = Path(__file__).parent / "fixtures"


def source() -> SourceConfig:
    return SourceConfig(
        id="example", name="Example", type="web", url="https://www.example.com/research/", content_role="research",
        discovery=DiscoveryConfig(include_path_regexes=[r"^/research/"], exclude_path_regexes=[r"^/research/?$"]),
    )


def test_card_dates_are_local_and_nav_footer_are_excluded() -> None:
    items = discover_from_html(source(), (FIXTURES / "cards.html").read_text(encoding="utf-8"))
    by_title = {item.anchor_text: item for item in items}
    assert set(by_title) == {"First paper", "Second paper", "Third paper"}
    assert by_title["First paper"].discovered_date.startswith("2026-09-10")
    assert by_title["Second paper"].discovered_date is None
    assert by_title["Third paper"].discovered_date.startswith("2026-09-11")


def test_feed_uses_xml_parser_without_warning() -> None:
    xml = (FIXTURES / "feed.xml").read_text(encoding="utf-8")
    feed_source = source().model_copy(update={"url": "https://example.com/feed", "discovery": DiscoveryConfig(mode="rss", renderer="http")})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        items = discover_from_feed(feed_source, xml)
    assert len(items) == 1
    assert not any(isinstance(w.message, XMLParsedAsHTMLWarning) for w in caught)
    assert items[0].discovered_date.startswith("2026-08-23")


def test_canonicalization_removes_fragment_tracking_and_www() -> None:
    assert canonicalize_url("https://www.example.com/article/?utm_source=x#respond") == canonicalize_url("https://example.com/article")
