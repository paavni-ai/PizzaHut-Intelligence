"""Run one auditable public Pizza Hut UAE menu collection.

The database URL is required from the runtime environment. This entrypoint
never prints credentials and returns non-zero for failed or partial runs so a
scheduler can report the failure accurately.
"""
import json
import sys

from src.db.connection import get_database_url
from src.scrapers.pizzahut_scraper import PizzaHutMenuScraper


def main() -> int:
    if not get_database_url():
        print("Collection not started: DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    try:
        result = PizzaHutMenuScraper().run_live_extraction("DXB")
    except Exception as exc:
        # Exception messages from database drivers can contain connection
        # details. Print only the exception class to keep secrets out of logs.
        print(f"Collection failed before completion ({type(exc).__name__}).", file=sys.stderr)
        return 1

    print(json.dumps({
        "run_uuid": result["run_uuid"],
        "status": result["status"],
        "items_extracted": result["items_extracted"],
        "items_verified": result["items_verified"],
        "error_count": len(result.get("errors", [])),
        "elapsed_ms": result["elapsed_ms"],
    }, sort_keys=True))
    if result.get("errors"):
        for error in result["errors"]:
            print(f"Collection issue: {error}", file=sys.stderr)
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
