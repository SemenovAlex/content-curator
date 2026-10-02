from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from curator.config import SourceConfig
from curator.models import DiscoveryCandidate
from curator.utils import canonicalize_url, normalize_text, parse_datetime, stable_hash, utcnow

DATE_TEXT_PATTERNS = [
    re.compile(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b", re.I),
    re.compile(r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b", re.I),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
]
BLOCKED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip", ".mp3", ".mp4", ".mov"}
BLOCKED_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "vk.com", "vkvideo.ru"}


def _matches_filters(url: str, source: SourceConfig) -> bool:
    parts = urlsplit(url)
    if parts.hostname in BLOCKED_HOSTS:
        return False
    if any(parts.path.casefold().endswith(ext) for ext in BLOCKED_EXTENSIONS):
        return False
    path = parts.path or "/"
    includes = source.discovery.include_path_regexes
    excludes = source.discovery.exclude_path_regexes
    if includes and not any(re.search(pattern, path) for pattern in includes):
        return False
    if excludes and any(re.search(pattern, path) for pattern in excludes):
        return False
    return True


def _remove_noise(soup: BeautifulSoup) -> None:
    for selector in ["header", "nav", "footer", "script", "style", "noscript"]:
        for node in soup.select(selector):
            node.decompose()


def _nearest_card(anchor: Tag) -> Tag:
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name in {"article", "li"}:
            return parent
        classes = " ".join(parent.get("class", []))
        if re.search(r"\b(card|post|article|item|entry|result|story)\b", classes, re.I):
            return parent
        if parent.name in {"main", "body"}:
            break
    return anchor.parent if isinstance(anchor.parent, Tag) else anchor


def _local_date(card: Tag) -> str | None:
    for time_tag in card.find_all("time"):
        value = time_tag.get("datetime") or normalize_text(time_tag.get_text(" ", strip=True))
        parsed = parse_datetime(value)
        if parsed:
            return parsed.isoformat()
    text = normalize_text(card.get_text(" ", strip=True))
    for pattern in DATE_TEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            parsed = parse_datetime(match.group(0))
            if parsed:
                return parsed.isoformat()
    return None


def _candidate(source: SourceConfig, fetch_url: str, anchor_text: str, context_text: str,
               discovered_date: str | None, discovered_at: datetime, metadata: dict | None = None) -> DiscoveryCandidate:
    canonical = canonicalize_url(fetch_url)
    return DiscoveryCandidate(
        source_id=source.id,
        source_name=source.name,
        source_role=source.content_role,
        fetch_url=fetch_url,
        canonical_url=canonical,
        discovered_from=source.url,
        anchor_text=anchor_text,
        context_text=context_text,
        context_fingerprint=stable_hash(context_text or canonical),
        discovered_date=discovered_date,
        discovered_at=discovered_at,
        metadata=metadata or {},
    )


def discover_from_html(source: SourceConfig, html: str, discovered_at: datetime | None = None) -> list[DiscoveryCandidate]:
    discovered_at = discovered_at or utcnow()
    soup = BeautifulSoup(html, "html.parser")
    _remove_noise(soup)
    landing_canonical = canonicalize_url(source.url)
    candidates: dict[str, DiscoveryCandidate] = {}
    main = soup.find("main") or soup.body or soup
    for anchor in main.find_all("a", href=True):
        href = normalize_text(anchor.get("href", ""))
        if not href or href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        fetch_url = urljoin(source.url, href)
        if not _matches_filters(fetch_url, source):
            continue
        canonical = canonicalize_url(fetch_url)
        if canonical == landing_canonical:
            continue
        card = _nearest_card(anchor)
        context = normalize_text(card.get_text(" ", strip=True))[:1800]
        anchor_text = normalize_text(anchor.get_text(" ", strip=True))
        if not anchor_text and not context:
            continue
        candidate = _candidate(
            source,
            fetch_url,
            anchor_text,
            context,
            _local_date(card),
            discovered_at,
            {"index": {"href": href}},
        )
        previous = candidates.get(candidate.canonical_url)
        if previous is None or (not previous.discovered_date and candidate.discovered_date):
            candidates[candidate.canonical_url] = candidate
    return list(candidates.values())


def _feed_entries(soup: BeautifulSoup) -> Iterable[Tag]:
    yield from soup.find_all(["item", "entry"])


def discover_from_feed(source: SourceConfig, xml: str, discovered_at: datetime | None = None) -> list[DiscoveryCandidate]:
    discovered_at = discovered_at or utcnow()
    soup = BeautifulSoup(xml, "xml")  # Deliberate XML parser; avoids XMLParsedAsHTMLWarning.
    candidates: dict[str, DiscoveryCandidate] = {}
    for entry in _feed_entries(soup):
        link_tag = entry.find("link")
        href = ""
        if link_tag:
            href = normalize_text(link_tag.get("href") or link_tag.get_text(strip=True))
        if not href:
            guid = entry.find("guid")
            href = normalize_text(guid.get_text(strip=True)) if guid else ""
        if not href:
            continue
        fetch_url = urljoin(source.url, href)
        if not _matches_filters(fetch_url, source):
            continue
        title_tag = entry.find("title")
        title = normalize_text(title_tag.get_text(" ", strip=True)) if title_tag else ""
        summary_tag = entry.find(["description", "summary", "content"])
        context = normalize_text(summary_tag.get_text(" ", strip=True)) if summary_tag else title
        date_tag = entry.find(["pubDate", "published", "updated", "date"])
        published = parse_datetime(date_tag.get_text(" ", strip=True)) if date_tag else None
        candidate = _candidate(
            source,
            fetch_url,
            title,
            context[:1800],
            published.isoformat() if published else None,
            discovered_at,
            {"index": {"feed_title": title}},
        )
        candidates[candidate.canonical_url] = candidate
    return list(candidates.values())


def parse_sitemap_urls(xml: str) -> set[str]:
    soup = BeautifulSoup(xml, "xml")
    return {
        canonicalize_url(normalize_text(loc.get_text(strip=True)))
        for loc in soup.find_all("loc")
        if normalize_text(loc.get_text(strip=True))
    }
