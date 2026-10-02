#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case:
    day: str
    source: str
    expected: str
    contains: bool = False


CASES = [
    Case("2026-09-07", "import_ai", "Import AI 472", contains=True),
    Case("2026-09-04", "the_batch", "Inside Key Changes in Data Policies, Ox Alpha Revealed, Taking Custom Models Beyond Fine-Tuning"),
    Case("2026-08-23", "one_useful_thing", "An opinionated guide to which AI to use to do stuff"),
    Case("2026-08-26", "metr_research", "Brief independent investigation of agents’ behavior, reasoning and collaboration in the OpenAI / Hugging Face hacking incident"),
    Case("2026-09-09", "ahead_of_ai", "GPT-6 Astra, Looped Transformers, and Hidden Reasoning"),
    Case("2026-09-04", "gurobi_blog", "Switching from FICO Xpress to Gurobi"),
    Case("2026-09-10", "anthropic_research", "Measuring tactical intelligence targeting and conventional weapons capabilities of AI models"),
    Case("2026-09-18", "anthropic_news", "Partnering with Accenture on embedded evaluation"),
    Case("2026-09-10", "openai_research", "Build more natural voice experiences with GPT‑Live‑1 in the API"),
    Case("2026-09-01", "deepmind_blog", "Introducing agentic video understanding with Gemini"),
    Case("2026-09-01", "huggingface_blog", "Introducing @huggingface/kernels: 200+ WebGPU Kernels for Local AI"),
    Case("2026-04-23", "anthropic_engineering", "An update on recent Claude Code quality reports"),
    Case("2026-09-01", "deepmind_research", "Designing Proactive Thought Partners for Writing"),
]


def norm(value: str) -> str:
    return " ".join(value.replace("‑", "-").replace("’", "'").split()).casefold()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=Path(".venv/bin/curator"))
    parser.add_argument("--config", type=Path, default=Path("sources.yaml"))
    parser.add_argument("--source")
    args = parser.parse_args()
    cases = [case for case in CASES if not args.source or case.source == args.source]
    failed = False
    results = []
    for case in cases:
        command = [
            str(args.cli), "ingest-articles", "--date", case.day, "--tz", "Europe/Moscow",
            "--sources", case.source, "--stateless", "--workers", "2", "--config", str(args.config),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = {"items": [], "errors": [{"error": completed.stderr or completed.stdout}]}
        titles = [str(item.get("title", "")) for item in payload.get("items", [])]
        expected = norm(case.expected)
        matched = [title for title in titles if (expected in norm(title) if case.contains else norm(title) == expected)]
        ok = completed.returncode == 0 and len(matched) == 1
        failed = failed or not ok
        results.append({
            "date": case.day, "source": case.source, "expected": case.expected,
            "matched": matched, "titles": titles, "errors": payload.get("errors", []), "ok": ok,
        })
    print(json.dumps({"ok": not failed, "cases": results}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
