from __future__ import annotations

from dataclasses import dataclass

import httpx

from curator.config import SourceConfig

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0 Safari/537.36 ContentCurator/0.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(slots=True)
class FetchResult:
    url: str
    text: str
    method: str
    status_code: int | None = None
    content_type: str = ""


class FetchError(RuntimeError):
    pass


def _looks_thin(html: str) -> bool:
    stripped = html.strip()
    if len(stripped) < 1200:
        return True
    lowered = stripped.casefold()
    return "<body" not in lowered and "<rss" not in lowered and "<feed" not in lowered


def fetch_http(url: str, timeout: float = 30.0) -> FetchResult:
    with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        return FetchResult(
            url=str(response.url),
            text=response.text,
            method="http",
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
        )


def fetch_browser(url: str, timeout_ms: int = 45_000) -> FetchResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise FetchError("browser renderer requested but playwright is not installed") from exc

    with sync_playwright() as playwright:  # pragma: no cover
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"])
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(750)
            return FetchResult(url=page.url, text=page.content(), method="browser")
        finally:
            browser.close()


def fetch_source_entry(source: SourceConfig) -> FetchResult:
    # RSS/Atom must remain XML fetched over HTTP; Chromium is only an article/page fallback.
    if source.discovery.mode == "rss":
        return fetch_http(source.url)
    if source.discovery.renderer == "browser":
        return fetch_browser(source.url)
    try:
        result = fetch_http(source.url)
    except httpx.HTTPError:
        if source.discovery.renderer == "http":
            raise
        return fetch_browser(source.url)
    if source.discovery.renderer == "auto" and _looks_thin(result.text):
        try:
            return fetch_browser(source.url)
        except Exception:
            return result
    return result


def fetch_article(url: str, renderer: str = "auto") -> FetchResult:
    if renderer == "browser":
        return fetch_browser(url)
    try:
        result = fetch_http(url)
    except httpx.HTTPError:
        if renderer == "http":
            raise
        return fetch_browser(url)
    if renderer == "auto" and _looks_thin(result.text):
        try:
            return fetch_browser(url)
        except Exception:
            return result
    return result
