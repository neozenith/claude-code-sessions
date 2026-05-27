"""One-shot trigger for the (session_id, uuid) dedupe migration.

Opens the live cache, runs ``CacheManager.migrate_dedupe_session_uuid()``,
and prints the result. The migration is sentinel-gated, so re-running this
script after a successful run is a no-op.

    uv run scripts/run_dedupe_migration.py
"""

from __future__ import annotations

import json
import logging
import sys

from claude_code_sessions.database.sqlite.cache import CacheManager


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    cache = CacheManager()
    try:
        result = cache.migrate_dedupe_session_uuid()
    finally:
        cache.close()

    if result is None:
        print("Migration already complete (sentinel set). Nothing to do.")
        return 0

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
