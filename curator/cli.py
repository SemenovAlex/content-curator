from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from curator.config import article_sources, load_config
from curator.finalize import finalize_day
from curator.models import AnalysisRecord
from curator.publish import publish_digest as publish_digest_file
from curator.service import discovery_for_day, ingest_articles, select_sources
from curator.statistics import compute_stats, render_chart
from curator.storage import (
    cleanup as cleanup_storage,
    data_dir,
    load_analysis,
    load_manifest,
    read_content as read_stored_content,
    save_analysis as save_analysis_record,
)
from curator.utils import json_dumps, utcnow

app = typer.Typer(add_completion=False, no_args_is_help=True, pretty_exceptions_enable=False)
DEFAULT_CONFIG = Path("sources.yaml")


def _emit(payload: object) -> None:
    typer.echo(json_dumps(payload))


def _fail(exc: Exception) -> None:
    _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
    raise typer.Exit(code=1) from exc


def _source_arg(value: str | None) -> list[str] | None:
    if value is None or not value.strip():
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


@app.command("article-sources")
def article_sources_command(config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG) -> None:
    try:
        sources = article_sources(load_config(config))
        _emit({"ok": True, "count": len(sources), "sources": [s.model_dump(mode="json") for s in sources]})
    except Exception as exc:
        _fail(exc)


@app.command("discover-articles")
def discover_articles_command(
    day: Annotated[str, typer.Option("--date")],
    tz: Annotated[str, typer.Option("--tz")] = "Europe/Moscow",
    sources: Annotated[str | None, typer.Option("--sources")] = None,
    workers: Annotated[int, typer.Option("--workers", min=1)] = 4,
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        target = date.fromisoformat(day)
        cfg = load_config(config)
        selected = select_sources(cfg, _source_arg(sources))
        candidates, errors = discovery_for_day(selected, target, tz, workers=workers)
        _emit({
            "ok": True,
            "date": day,
            "timezone": tz,
            "source_ids": [source.id for source in selected],
            "items": [candidate.model_dump(mode="json") for candidate in candidates],
            "errors": [error.model_dump(mode="json") for error in errors],
        })
    except Exception as exc:
        _fail(exc)


@app.command("ingest-articles")
def ingest_articles_command(
    day: Annotated[str, typer.Option("--date")],
    tz: Annotated[str, typer.Option("--tz")] = "Europe/Moscow",
    sources: Annotated[str | None, typer.Option("--sources")] = None,
    stateless: Annotated[bool, typer.Option("--stateless")] = False,
    workers: Annotated[int, typer.Option("--workers", min=1)] = 4,
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        target = date.fromisoformat(day)
        cfg = load_config(config)
        selected = select_sources(cfg, _source_arg(sources))
        manifest = ingest_articles(cfg, selected, target, tz, data_dir(config), workers=workers, stateless=stateless)
        _emit(manifest.model_dump(mode="json"))
    except Exception as exc:
        _fail(exc)


@app.command("list-ingest")
def list_ingest_command(
    day: Annotated[str, typer.Option("--date")],
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        manifest = load_manifest(data_dir(config), day)
        if manifest is None:
            raise FileNotFoundError(f"ingest manifest not found for {day}")
        _emit(manifest.model_dump(mode="json"))
    except Exception as exc:
        _fail(exc)


@app.command("read-content")
def read_content_command(
    content_id: str,
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        metadata, text = read_stored_content(data_dir(config), content_id)
        _emit({"ok": True, "content_id": content_id, "metadata": metadata, "text": text})
    except Exception as exc:
        _fail(exc)


@app.command("save-analysis")
def save_analysis_command(
    content_id: str,
    day: Annotated[str, typer.Option("--date")],
    category: Annotated[str, typer.Option("--category")],
    score: Annotated[int, typer.Option("--score", min=1, max=10)],
    reason: Annotated[str, typer.Option("--reason")],
    summary: Annotated[str, typer.Option("--summary")],
    topics: Annotated[str, typer.Option("--topics")] = "",
    language: Annotated[str | None, typer.Option("--language")] = None,
    reading_minutes: Annotated[int | None, typer.Option("--reading-minutes", min=0)] = None,
    insights_json: Annotated[str, typer.Option("--insights-json")] = "[]",
    entities_json: Annotated[str, typer.Option("--entities-json")] = "[]",
    takeaways_json: Annotated[str, typer.Option("--takeaways-json")] = "[]",
    verdict: Annotated[str | None, typer.Option("--verdict")] = None,
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        record = AnalysisRecord(
            date=day,
            content_id=content_id,
            category=category,  # type: ignore[arg-type]
            score=score,
            reason=reason,
            summary=summary,
            topics=[part.strip() for part in topics.split(",") if part.strip()],
            language=language,
            reading_minutes=reading_minutes,
            insights=json.loads(insights_json),
            entities=json.loads(entities_json),
            takeaways=json.loads(takeaways_json),
            verdict=verdict,
            analyzed_at=utcnow(),
        )
        save_analysis_record(data_dir(config), record)
        _emit({"ok": True, "analysis": record.model_dump(mode="json")})
    except Exception as exc:
        _fail(exc)


@app.command("list-analysis")
def list_analysis_command(
    day: Annotated[str, typer.Option("--date")],
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        records = load_analysis(data_dir(config), day)
        _emit({"ok": True, "date": day, "analysis": [record.model_dump(mode="json") for record in records]})
    except Exception as exc:
        _fail(exc)


@app.command("finalize-day")
def finalize_day_command(
    day: Annotated[str, typer.Option("--date")],
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        finalized = finalize_day(data_dir(config), day)
        _emit({"ok": True, **finalized.model_dump(mode="json")})
    except Exception as exc:
        _fail(exc)


@app.command("publish-digest")
def publish_digest_command(
    day: Annotated[str, typer.Option("--date")],
    input_path: Annotated[Path, typer.Option("--input")],
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        destination = publish_digest_file(data_dir(config), day, input_path)
        _emit({"ok": True, "date": day, "path": str(destination)})
    except Exception as exc:
        _fail(exc)


@app.command("stats")
def stats_command(
    start: Annotated[str, typer.Option("--from")],
    end: Annotated[str, typer.Option("--to")],
    chart: Annotated[Path | None, typer.Option("--chart")] = None,
    config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG,
) -> None:
    try:
        result = compute_stats(data_dir(config), date.fromisoformat(start), date.fromisoformat(end))
        if chart is not None:
            render_chart(result, chart)
            result["chart"] = str(chart.resolve())
        _emit({"ok": True, **result})
    except Exception as exc:
        _fail(exc)


@app.command("cleanup")
def cleanup_command(config: Annotated[Path, typer.Option("--config")] = DEFAULT_CONFIG) -> None:
    try:
        cfg = load_config(config)
        result = cleanup_storage(
            data_dir(config),
            raw_days=cfg.retention.raw_retention_days,
            content_days=cfg.retention.full_content_retention_days,
            max_storage_gb=cfg.retention.max_storage_gb,
        )
        _emit({"ok": True, **result})
    except Exception as exc:
        _fail(exc)


if __name__ == "__main__":
    app()
