from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

from curator.config import CuratorConfig, SourceConfig, article_sources
from curator.discover import discover_from_feed, discover_from_html, parse_sitemap_urls
from curator.extract import extract_article
from curator.fetch import fetch_article, fetch_http, fetch_source_entry
from curator.models import DiscoveryCandidate, IngestError, IngestItem, IngestManifest
from curator.storage import load_manifest, load_state, replace_jsonl_slice, save_content, save_manifest, save_state
from curator.utils import content_id_for_url, date_in_timezone, parse_datetime, utcnow


def select_sources(config: CuratorConfig, requested: list[str] | None) -> list[SourceConfig]:
    available = {source.id: source for source in article_sources(config)}
    if not requested:
        return list(available.values())
    missing = [source_id for source_id in requested if source_id not in available]
    if missing:
        raise ValueError(f"unknown or non-article sources: {', '.join(missing)}")
    return [available[source_id] for source_id in requested]


def _load_sitemap_allowlist(source: SourceConfig) -> set[str] | None:
    if not source.discovery.allowlist_sitemaps:
        return None
    allowed: set[str] = set()
    queue = list(source.discovery.allowlist_sitemaps)
    seen: set[str] = set()
    while queue and len(seen) < 100:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen:
            continue
        seen.add(sitemap_url)
        result = fetch_http(sitemap_url)
        urls = parse_sitemap_urls(result.text)
        for url in urls:
            if url.endswith(".xml/") or url.endswith(".xml"):
                queue.append(url.rstrip("/"))
            else:
                allowed.add(url)
    return allowed


def _openai_feed_filter(source: SourceConfig, candidates: list[DiscoveryCandidate], raw_xml: str) -> list[DiscoveryCandidate]:
    # OpenAI's RSS is the configured discovery entry point. Scope enforcement is
    # performed by the explicitly allowlisted research/release sitemaps below,
    # rather than brittle RSS category labels that publishers can rename.
    return candidates


def discover_one(source: SourceConfig) -> tuple[list[DiscoveryCandidate], list[IngestError]]:
    try:
        result = fetch_source_entry(source)
        is_feed = source.discovery.mode == "rss" or "xml" in result.content_type or result.text.lstrip().startswith(("<?xml", "<rss", "<feed"))
        candidates = discover_from_feed(source, result.text) if is_feed else discover_from_html(source, result.text)
        if is_feed:
            candidates = _openai_feed_filter(source, candidates, result.text)
        allowlist = _load_sitemap_allowlist(source)
        if allowlist:
            candidates = [candidate for candidate in candidates if candidate.canonical_url in allowlist]
        return candidates, []
    except Exception as exc:
        return [], [IngestError(source_id=source.id, stage="discovery", url=source.url, error=str(exc))]


def discover_many(sources: list[SourceConfig], workers: int = 4) -> tuple[list[DiscoveryCandidate], list[IngestError]]:
    candidates: list[DiscoveryCandidate] = []
    errors: list[IngestError] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(discover_one, source): source for source in sources}
        for future in as_completed(futures):
            found, found_errors = future.result()
            candidates.extend(found)
            errors.extend(found_errors)
    candidates.sort(key=lambda item: (item.source_id, item.canonical_url))
    return candidates, errors


def discovery_for_day(sources: list[SourceConfig], target: date, tz_name: str, workers: int = 4) -> tuple[list[DiscoveryCandidate], list[IngestError]]:
    candidates, errors = discover_many(sources, workers=workers)
    selected = []
    for candidate in candidates:
        parsed = parse_datetime(candidate.discovered_date)
        if parsed and date_in_timezone(parsed, tz_name) == target:
            selected.append(candidate)
    return selected, errors


def _error_item(target: date, source: SourceConfig, candidate: DiscoveryCandidate, error: Exception) -> IngestItem:
    return IngestItem(
        date=target.isoformat(),
        source_id=source.id,
        content_id=content_id_for_url(candidate.canonical_url),
        title=candidate.anchor_text or "Unprocessed article",
        source_name=source.name,
        source_role=source.content_role,
        url=candidate.fetch_url,
        canonical_url=candidate.canonical_url,
        discovered_from=candidate.discovered_from,
        published_at=parse_datetime(candidate.discovered_date),
        discovered_at=candidate.discovered_at,
        extraction_status="error",
        extraction_method="error",
        metadata={"index": candidate.metadata.get("index", {}), "error": str(error)},
    )


def ingest_source(source: SourceConfig, candidates: list[DiscoveryCandidate], target: date, tz_name: str,
                  root: Path, stateless: bool) -> tuple[list[IngestItem], list[IngestError], list[dict[str, Any]]]:
    items: list[IngestItem] = []
    errors: list[IngestError] = []
    extraction_rows: list[dict[str, Any]] = []
    state = {"source_id": source.id, "items": {}} if stateless else load_state(root, source.id)
    known: dict[str, Any] = state.setdefault("items", {})

    for candidate in candidates:
        candidate_date = parse_datetime(candidate.discovered_date)
        if not candidate_date and stateless:
            # Historical stateless run cannot accept an item whose index/feed did not date it.
            continue
        if not candidate_date:
            candidate_date = parse_datetime(known.get(candidate.canonical_url, {}).get("published_at"))
        if candidate_date and date_in_timezone(candidate_date, tz_name) != target:
            continue

        content_id = content_id_for_url(candidate.canonical_url)
        try:
            fetched = fetch_article(candidate.fetch_url, renderer=source.discovery.renderer)
            extracted = extract_article(fetched.text, fetched.url, fallback_title=candidate.anchor_text)
            published = extracted.published_at or candidate_date
            if published is None or date_in_timezone(published, tz_name) != target:
                continue
            if len(extracted.text.strip()) < 200:
                raise ValueError("article body extraction returned less than 200 characters")
            text_file = save_content(
                root,
                content_id,
                target.isoformat(),
                extracted.text,
                {
                    "content_id": content_id,
                    "canonical_url": candidate.canonical_url,
                    "fetch_url": candidate.fetch_url,
                    "source_id": source.id,
                    "published_at": published.isoformat(),
                    "title": extracted.title,
                },
            )
            item = IngestItem(
                date=target.isoformat(),
                source_id=source.id,
                content_id=content_id,
                title=extracted.title,
                source_name=source.name,
                source_role=source.content_role,
                url=candidate.fetch_url,
                canonical_url=candidate.canonical_url,
                discovered_from=candidate.discovered_from,
                published_at=published,
                discovered_at=candidate.discovered_at,
                description=extracted.description,
                extraction_status="ok",
                extraction_method=f"{fetched.method}+{extracted.method}",
                text_file=text_file,
                excerpt=extracted.text[:1200].strip(),
                metadata={
                    "index": candidate.metadata.get("index", {}),
                    "content": extracted.metadata,
                    "context_fingerprint": candidate.context_fingerprint,
                },
            )
            items.append(item)
            extraction_rows.append(item.model_dump(mode="json"))
            known[candidate.canonical_url] = {
                "published_at": published.isoformat(),
                "title": extracted.title,
                "last_seen_at": utcnow().isoformat(),
            }
        except Exception as exc:
            errors.append(IngestError(source_id=source.id, stage="extraction", url=candidate.fetch_url, error=str(exc)))
            if candidate_date and date_in_timezone(candidate_date, tz_name) == target:
                item = _error_item(target, source, candidate, exc)
                items.append(item)
                extraction_rows.append(item.model_dump(mode="json"))

    if not stateless:
        state["updated_at"] = utcnow().isoformat()
        save_state(root, source.id, state)
    return items, errors, extraction_rows


def ingest_articles(config: CuratorConfig, selected_sources: list[SourceConfig], target: date, tz_name: str,
                    root: Path, workers: int = 4, stateless: bool = False) -> IngestManifest:
    candidates, discovery_errors = discover_many(selected_sources, workers=workers)
    by_source: dict[str, list[DiscoveryCandidate]] = {source.id: [] for source in selected_sources}
    for candidate in candidates:
        by_source.setdefault(candidate.source_id, []).append(candidate)

    run_items: list[IngestItem] = []
    run_errors = list(discovery_errors)
    extraction_rows: list[dict[str, Any]] = []
    for source in selected_sources:
        items, errors, rows = ingest_source(source, by_source.get(source.id, []), target, tz_name, root, stateless)
        run_items.extend(items)
        run_errors.extend(errors)
        extraction_rows.extend(rows)

    source_ids = [source.id for source in selected_sources]
    stats = {
        source.id: {
            "discovered": len(by_source.get(source.id, [])),
            "accepted": sum(1 for item in run_items if item.source_id == source.id),
            "errors": sum(1 for error in run_errors if error.source_id == source.id),
        }
        for source in selected_sources
    }
    run_manifest = IngestManifest(
        date=target.isoformat(), timezone=tz_name, generated_at=utcnow(), source_ids=source_ids,
        items=sorted(run_items, key=lambda item: (item.source_id, item.content_id)), errors=run_errors, stats=stats,
    )

    day_dir = root / "runs" / target.isoformat()
    replace_jsonl_slice(day_dir / "discoveries.jsonl", "source_id", set(source_ids), [c.model_dump(mode="json") for c in candidates])
    replace_jsonl_slice(day_dir / "extraction.jsonl", "source_id", set(source_ids), extraction_rows)

    existing = load_manifest(root, target.isoformat())
    selected = set(source_ids)
    preserved_items = [item for item in existing.items if item.source_id not in selected] if existing else []
    preserved_errors = [error for error in existing.errors if error.source_id not in selected] if existing else []
    preserved_stats = {key: value for key, value in existing.stats.items() if key not in selected} if existing else {}
    preserved_sources = [source_id for source_id in existing.source_ids if source_id not in selected] if existing else []
    cumulative = IngestManifest(
        date=target.isoformat(), timezone=tz_name, generated_at=utcnow(), source_ids=preserved_sources + source_ids,
        items=sorted(preserved_items + run_items, key=lambda item: (item.source_id, item.content_id)),
        errors=preserved_errors + run_errors, stats={**preserved_stats, **stats},
    )
    save_manifest(root, cumulative)
    return run_manifest
