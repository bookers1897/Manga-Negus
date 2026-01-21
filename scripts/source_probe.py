#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional


def load_env(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key and key not in os.environ:
                os.environ[key] = value


def _duration_ms(start: float) -> int:
    return int((time.time() - start) * 1000)


def probe_source(
    source,
    query: str,
    deep: bool,
    fetch_pages: bool,
    allow_empty: bool
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "source_id": source.id,
        "source_name": source.name,
        "available": bool(source.is_available),
        "search_ok": False,
        "search_count": 0,
        "search_ms": None,
        "chapters_ok": False,
        "chapters_count": 0,
        "chapters_ms": None,
        "pages_ok": False,
        "pages_count": 0,
        "pages_ms": None,
        "errors": []
    }

    start = time.time()
    try:
        search_results = source.search(query, page=1)
        result["search_ok"] = True
        result["search_count"] = len(search_results or [])
    except Exception as exc:
        result["errors"].append(f"search: {exc}")
        search_results = []
    result["search_ms"] = _duration_ms(start)

    if not allow_empty and result["search_ok"] and not search_results:
        last_error = getattr(source, "_last_error", None)
        if last_error:
            result["search_ok"] = False
            result["errors"].append(f"search_empty: {last_error}")

    if not deep or not search_results:
        return result

    manga = search_results[0]
    start = time.time()
    try:
        chapters = source.get_chapters(manga.id, "en")
        result["chapters_ok"] = True
        result["chapters_count"] = len(chapters or [])
    except Exception as exc:
        result["errors"].append(f"chapters: {exc}")
        chapters = []
    result["chapters_ms"] = _duration_ms(start)

    if not allow_empty and result["chapters_ok"] and not chapters:
        last_error = getattr(source, "_last_error", None)
        if last_error:
            result["chapters_ok"] = False
            result["errors"].append(f"chapters_empty: {last_error}")

    if not fetch_pages or not chapters:
        return result

    chapter = chapters[0]
    start = time.time()
    try:
        pages = source.get_pages(chapter.id)
        result["pages_ok"] = True
        result["pages_count"] = len(pages or [])
    except Exception as exc:
        result["errors"].append(f"pages: {exc}")
    result["pages_ms"] = _duration_ms(start)

    return result


def build_ordered_sources(manager, requested: Optional[List[str]], limit: Optional[int]) -> List[Any]:
    all_sources = {source.id: source for source in manager.list_sources()}
    if requested:
        ordered = [all_sources[sid] for sid in requested if sid in all_sources]
    else:
        priority = list(getattr(manager, "_priority_order", []))
        ordered = []
        for sid in priority:
            if sid in all_sources:
                ordered.append(all_sources[sid])
        for sid in sorted(all_sources.keys()):
            if sid not in {src.id for src in ordered}:
                ordered.append(all_sources[sid])

    if limit is not None and limit > 0:
        ordered = ordered[:limit]
    return ordered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe manga sources for basic health.")
    parser.add_argument("--query", default="one piece", help="Search query to test.")
    parser.add_argument("--sources", default="", help="Comma-separated source IDs to test.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of sources to test.")
    parser.add_argument("--deep", action="store_true", help="Also fetch chapters for first result.")
    parser.add_argument("--pages", action="store_true", help="Also fetch pages for first chapter.")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Do not treat empty results as failures."
    )
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep seconds between sources.")
    parser.add_argument(
        "--output",
        default="/opt/manganegus/debugging/source_probe.json",
        help="Output JSON report path."
    )
    parser.add_argument(
        "--env",
        default="/opt/manganegus/.env",
        help="Path to .env file for scraper settings."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env(args.env)

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    from sources import get_source_manager  # pylint: disable=import-outside-toplevel

    manager = get_source_manager()

    requested = [item.strip() for item in args.sources.split(",") if item.strip()]
    limit = args.limit if args.limit > 0 else None
    ordered_sources = build_ordered_sources(manager, requested or None, limit)

    results = []
    for source in ordered_sources:
        results.append(probe_source(
            source,
            args.query,
            args.deep,
            args.pages,
            args.allow_empty
        ))
        if args.sleep:
            time.sleep(args.sleep)

    failures = sum(1 for item in results if not item["search_ok"])
    chapter_failures = sum(
        1 for item in results
        if args.deep and item["search_ok"] and not item["chapters_ok"]
    )
    page_failures = sum(
        1 for item in results
        if args.pages and item["chapters_ok"] and not item["pages_ok"]
    )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "query": args.query,
        "deep": bool(args.deep),
        "pages": bool(args.pages),
        "total_sources": len(results),
        "search_failures": failures,
        "chapter_failures": chapter_failures,
        "page_failures": page_failures,
        "sources": results
    }

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    print(f"Wrote report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
