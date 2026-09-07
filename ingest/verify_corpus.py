"""Verify what actually landed in the corpus tables. Read-only.

Prints PASS/FAIL per check rather than raw rows, so a problem cannot be
missed by skimming. Uses asyncpg (already an ingest dependency), so it needs
no psql on the PATH.

    cd ingest
    AGRIAI_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
      python verify_corpus.py
"""
import asyncio
import sys

import asyncpg

from config import settings
from sources import load_approved_items

EXPECTED_DIM = 384

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(label)


async def main() -> int:
    if not settings.database_url:
        print("AGRIAI_DATABASE_URL is not set.")
        return 1

    conn = await asyncpg.connect(settings.database_url)
    try:
        print("=== documents ===")
        docs = await conn.fetch(
            "select handle, title, doc_type, licence, published_year, page_count,"
            " language from public.documents order by handle"
        )
        for d in docs:
            print(
                f"  {d['handle']} | {d['doc_type']} | {d['licence']} | "
                f"{d['published_year']} | {d['page_count']}p | {d['title'][:44]}"
            )
        check("2 documents present", len(docs) == 2, f"found {len(docs)}")

        print("\n=== chunks per document ===")
        rows = await conn.fetch(
            """
            select d.handle,
                   count(*) as chunks,
                   count(c.page_no) as with_page,
                   count(c.section_path) as with_section,
                   count(c.crop_id) as with_crop,
                   min(c.page_no) as min_pg, max(c.page_no) as max_pg
            from public.chunks c
            join public.documents d on d.id = c.document_id
            group by d.handle order by d.handle
            """
        )
        per_doc = {}
        for r in rows:
            per_doc[r["handle"]] = r["chunks"]
            print(
                f"  {r['handle']}: {r['chunks']} chunks | page {r['min_pg']}-{r['max_pg']} | "
                f"with_page={r['with_page']} section={r['with_section']} crop={r['with_crop']}"
            )
            check(
                f"{r['handle']}: every chunk has page_no + section_path",
                r["with_page"] == r["chunks"] and r["with_section"] == r["chunks"],
            )

        total = sum(per_doc.values())
        check("total chunks == 113", total == 113, f"found {total}")

        print("\n=== exclusions (sources.yaml) ===")
        for item in load_approved_items():
            if not item.exclude_pages:
                continue
            leaked = await conn.fetch(
                """
                select c.page_no, count(*) as n
                from public.chunks c join public.documents d on d.id = c.document_id
                where d.handle = $1 and c.page_no = any($2::int[])
                group by c.page_no order by c.page_no
                """,
                item.handle,
                sorted(item.exclude_pages),
            )
            check(
                f"{item.handle}: pages {sorted(item.exclude_pages)} absent from corpus",
                not leaked,
                "" if not leaked else f"LEAKED {[(r['page_no'], r['n']) for r in leaked]}",
            )

        print("\n=== embeddings and lexical index ===")
        e = await conn.fetchrow(
            """
            select count(*) as total,
                   count(embedding) as with_embedding,
                   count(*) filter (where tsv is not null and tsv <> ''::tsvector) as with_tsv
            from public.chunks
            """
        )
        print(
            f"  total={e['total']} embedded={e['with_embedding']} tsv={e['with_tsv']}"
        )
        check("every chunk embedded", e["with_embedding"] == e["total"])
        check("every chunk has a non-empty tsv", e["with_tsv"] == e["total"])

        # Dimension and normalisation are checked in Python from the vector's
        # text form, rather than through a pgvector helper function whose exact
        # name would be a guess. The column is declared vector(384), so a wrong
        # dimension could not have been inserted -- this confirms it end to end
        # anyway, and confirms the L2 normalisation the cosine HNSW index
        # assumes (see the corpus migration).
        sample = await conn.fetch(
            "select embedding::text as v from public.chunks"
            " where embedding is not null order by random() limit 20"
        )
        dims, norms = set(), []
        for row in sample:
            vals = [float(x) for x in row["v"].strip("[]").split(",")]
            dims.add(len(vals))
            norms.append(sum(v * v for v in vals) ** 0.5)
        if norms:
            print(
                f"  sampled {len(norms)} vectors: dims={sorted(dims)} "
                f"L2 norm min={min(norms):.4f} max={max(norms):.4f}"
            )
            check(f"sampled embeddings are {EXPECTED_DIM}-dim", dims == {EXPECTED_DIM}, str(sorted(dims)))
            check(
                "sampled embeddings are L2-normalised (cosine index assumes it)",
                0.99 <= min(norms) and max(norms) <= 1.01,
            )
        else:
            check("embeddings present to sample", False, "none found")

        print("\n=== crop / state metadata ===")
        for r in await conn.fetch(
            """
            select d.handle, coalesce(cr.name_en,'(none)') as crop,
                   coalesce(c.state,'(none)') as state, count(*) as n
            from public.chunks c
            join public.documents d on d.id = c.document_id
            left join public.crops cr on cr.id = c.crop_id
            group by 1,2,3 order by 1,2
            """
        ):
            print(f"  {r['handle']}: crop={r['crop']}, state={r['state']} -> {r['n']} chunks")

        print("\n=== sample chunks ===")
        for r in await conn.fetch(
            "select page_no, section_path, token_count, left(content, 88) as c"
            " from public.chunks order by random() limit 3"
        ):
            print(f"  p{r['page_no']} [{(r['section_path'] or '')[:28]}] {r['token_count']}tok: {r['c']}...")
    finally:
        await conn.close()

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
