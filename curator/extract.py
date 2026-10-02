from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import trafilatura
from bs4 import BeautifulSoup

from curator.utils import is_generic_title, normalize_text, parse_datetime


@dataclass(slots=True)
class ExtractedArticle:
    title: str
    description: str
    published_at: datetime | None
    text: str
    method: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return normalize_text(tag["content"])
    return ""


def _iter_json_ld(soup: BeautifulSoup):
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                yield from (node for node in item["@graph"] if isinstance(node, dict))
            elif isinstance(item, dict):
                yield item


def _json_ld_fields(soup: BeautifulSoup) -> tuple[str, str, datetime | None, dict[str, Any]]:
    for item in _iter_json_ld(soup):
        kind = item.get("@type")
        kinds = {kind} if isinstance(kind, str) else set(kind or [])
        if not kinds.intersection({"Article", "NewsArticle", "BlogPosting", "TechArticle", "ScholarlyArticle"}):
            continue
        title = normalize_text(str(item.get("headline") or item.get("name") or ""))
        description = normalize_text(str(item.get("description") or ""))
        published = None
        for key in ("datePublished", "dateCreated", "uploadDate"):
            published = parse_datetime(item.get(key))
            if published:
                break
        return title, description, published, item
    return "", "", None, {}


def _title(soup: BeautifulSoup, json_title: str, fallback_title: str) -> tuple[str, str]:
    choices = [(_meta(soup, "og:title", "twitter:title"), "metadata"), (json_title, "json-ld")]
    h1 = soup.find("h1")
    if h1:
        choices.append((normalize_text(h1.get_text(" ", strip=True)), "h1"))
    choices.append((fallback_title, "index-card"))
    for value, origin in choices:
        if value and not is_generic_title(value):
            return value, origin
    return normalize_text(fallback_title) or "Untitled article", "fallback"


def _normalize_article_title(
    title: str,
    soup: BeautifulSoup,
    url: str,
    origin: str,
) -> tuple[str, str]:
    host = (urlsplit(url).hostname or "").casefold()
    value = normalize_text(title)

    # Gurobi exposes an SEO/site suffix in page metadata while the article
    # heading itself does not contain it.
    if host.endswith("gurobi.com"):
        value = re.sub(r"\s*\|\s*Gurobi\s*$", "", value, flags=re.I).strip()

    # Anthropic's SEO title can be a shortened/rephrased variant of the
    # visible publication title. For article detail pages, use the explicit
    # non-generic H1 as the publication title.
    if host.endswith("anthropic.com"):
        h1 = soup.find("h1")
        if h1:
            h1_title = normalize_text(h1.get_text(" ", strip=True))
            if h1_title and not is_generic_title(h1_title):
                return h1_title, "h1"

    return value, origin


def _published_at(soup: BeautifulSoup, json_date: datetime | None) -> tuple[datetime | None, str | None]:
    for name in ("article:published_time", "datePublished", "dateCreated", "uploadDate", "publication_date", "publish-date", "date"):
        parsed = parse_datetime(_meta(soup, name))
        if parsed:
            return parsed, f"meta:{name}"
    if json_date:
        return json_date, "json-ld"
    h1 = soup.find("h1")
    if h1:
        container = h1.parent
        for tag in container.find_all("time", limit=3) if container else []:
            parsed = parse_datetime(tag.get("datetime") or tag.get_text(" ", strip=True))
            if parsed:
                return parsed, "near-h1"
        text = normalize_text(container.get_text(" ", strip=True)) if container else ""
        match = re.search(
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b",
            text,
            re.I,
        )
        if match:
            parsed = parse_datetime(match.group(0))
            if parsed:
                return parsed, "near-h1"
    return None, None


def _fallback_text(soup: BeautifulSoup) -> tuple[str, str]:
    for name in ("main", "article", "body"):
        node = soup.find(name)
        if node:
            for noise in node.select("nav, footer, script, style, noscript, form"):
                noise.decompose()
            text = "\n\n".join(
                normalize_text(part.get_text(" ", strip=True))
                for part in node.find_all(["p", "li", "h2", "h3"])
                if normalize_text(part.get_text(" ", strip=True))
            )
            if len(text) >= 200:
                return text, name
    return "", "none"


def extract_article(html: str, url: str, fallback_title: str = "") -> ExtractedArticle:
    soup = BeautifulSoup(html, "html.parser")
    json_title, json_description, json_date, json_raw = _json_ld_fields(soup)
    title, title_origin = _title(soup, json_title, fallback_title)
    title, title_origin = _normalize_article_title(title, soup, url, title_origin)
    description = _meta(soup, "og:description", "description", "twitter:description") or json_description
    published_at, date_origin = _published_at(soup, json_date)
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
        deduplicate=True,
    ) or ""
    text = text.strip()
    method = "trafilatura"
    if len(text) < 200:
        text, method = _fallback_text(soup)
    return ExtractedArticle(
        title=title,
        description=description,
        published_at=published_at,
        text=text,
        method=method,
        metadata={"title_origin": title_origin, "date_origin": date_origin, "json_ld": json_raw},
    )
