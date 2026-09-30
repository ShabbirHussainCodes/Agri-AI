"""Write each document's `crops_covered` (ADR-0014) from sources.yaml into
public.documents, WITHOUT re-parsing or re-embedding anything.

Why a separate script: crop scope is a human review decision that can change
after a document is ingested, and a full run.py re-ingest costs a Docling
parse (~6 GB RAM) plus re-embedding every chunk just to update one column.
run.py writes the same column on every normal ingest, so the two never
disagree about where the value comes from: sources.yaml.

    cd ingest
    python sync_crops_covered.py --dry-run   # show what would change
    python sync_crops_covered.py
"""
import argparse
import asyncio
import sys

import asyncpg

from config import settings
from sources import load_approved_items


async def main_async(dry_run: bool) -> int:
    if not settings.database_url:
        print("AGRIAI_DATABASE_URL is not set (see .env.example).")
        return 1
    items = load_approved_items()
    conn = await asyncpg.connect(settings.database_url)
    try:
        missing = 0
        for item in items:
            row = await conn.fetchrow(
                "select crops_covered from public.documents where handle = $1", item.handle
            )
            if row is None:
                print(f"  ! {item.handle}: not in the database -- ingest it with run.py first")
                missing += 1
                continue
            new = list(item.crops_covered)
            old = list(row["crops_covered"])
            if old == new:
                print(f"  = {item.handle}: unchanged {new}")
                continue
            print(f"  ~ {item.handle}: {old} -> {new}")
            if not dry_run:
                await conn.execute(
                    "update public.documents set crops_covered = $2 where handle = $1",
                    item.handle,
                    new,
                )
        print("[dry run] nothing written" if dry_run else "Done.")
        return 1 if missing else 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync documents.crops_covered from sources.yaml")
    ap.add_argument("--dry-run", action="store_true")
    return asyncio.run(main_async(ap.parse_args().dry_run))


if __name__ == "__main__":
    sys.exit(main())
