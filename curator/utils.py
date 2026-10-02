from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}
GENERIC_TITLES = {"research", "news", "explore research", "deeplearning.ai", "google deepmind", "anthropic"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stable_hash(value: str, length: int = 20) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def content_id_for_url(canonical_url: str) -> str:
    return f"article:{stable_hash(canonical_url)}"


def canonicalize_url(url: str, base_url: str | None = None) -> str:
    absolute = urljoin(base_url or url, url)
    parts = urlsplit(absolute)
    scheme = parts.scheme.lower() or "https"
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/") + "/"
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower().startswith("utm_") or key.lower() in TRACKING_QUERY_KEYS:
            continue
        query.append((key, value))
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def date_in_timezone(value: datetime, tz_name: str) -> date:
    return value.astimezone(ZoneInfo(tz_name)).date()


def json_dumps(data: object) -> str:
    def default(value: object) -> str:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    return json.dumps(data, ensure_ascii=False, indent=2, default=default)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{stable_hash(content, 8)}.tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def is_generic_title(value: str) -> bool:
    normalized = normalize_text(value).casefold()
    return normalized in GENERIC_TITLES or len(normalized) < 4
