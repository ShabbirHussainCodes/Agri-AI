"""Postgres writes for the corpus tables (public.documents / public.chunks).

Ingestion connects directly to Postgres and therefore bypasses RLS. That is
deliberate and matches the corpus migration: the corpus has a read-only policy
for `authenticated` and no write policy at all, so it can only ever be written
by this job. Nothing here should ever run inside the API process.
"""
import asyncpg
import numpy as np

from parse_chunk import ParsedChunk
from sources import ApprovedItem


async def resolve_crop_id(conn: asyncpg.Connection, crop_name: str | None):
    """Map a crop name from sources.yaml onto public.crops.

    Raises instead of silently storing NULL: a typo'd crop name would quietly
    disable the crop filter for that whole document, and the failure would
    only ever show up as slightly worse retrieval.
    """
    if not crop_name:
        return None
    row = await conn.fetchrow(
        "select id from public.crops where name_en ilike $1", crop_name
    )
    if row is None:
        raise ValueError(
            f"crop_name {crop_name!r} in sources.yaml matches no row in "
            "public.crops -- fix the name or add the crop in a migration."
        )
    return row["id"]


async def upsert_document(
    conn: asyncpg.Connection,
    item: ApprovedItem,
    file_sha256: str,
    page_count: int | None,
):
    """Insert or refresh the document row, keyed on its repository handle so
    re-running ingestion updates in place instead of duplicating."""
    row = await conn.fetchrow(
        """
        insert into public.documents (
            source_id, handle, title, publisher, published_year,
            doc_type, licence, url, language, file_sha256, page_count
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        on conflict (handle) do update set
            source_id      = excluded.source_id,
            title          = excluded.title,
            publisher      = excluded.publisher,
            published_year = excluded.published_year,
            doc_type       = excluded.doc_type,
            licence        = excluded.licence,
            url            = excluded.url,
            language       = excluded.language,
            file_sha256    = excluded.file_sha256,
            page_count     = excluded.page_count,
            ingested_at    = now()
        returning id
        """,
        item.source_id,
        item.handle,
        item.title,
        item.publisher,
        item.year,
        item.doc_type,
        item.licence,
        item.item_url,
        item.language,
        file_sha256,
        page_count,
    )
    return row["id"]


def _vector_literal(vec: np.ndarray) -> str:
    """pgvector's text input format. Sent as text and cast in SQL so we do not
    need a custom asyncpg codec for one insert path."""
    return "[" + ",".join(repr(float(v)) for v in vec) + "]"


async def replace_chunks(
    conn: asyncpg.Connection,
    document_id,
    item: ApprovedItem,
    chunks: list[ParsedChunk],
    embeddings: np.ndarray | None,
    crop_id,
    token_counts: list[int] | None = None,
) -> int:
    """Delete-then-insert inside one transaction, so a document is never left
    half re-ingested and chunk_index never collides with a previous run."""
    rows = []
    for i, chunk in enumerate(chunks):
        rows.append(
            (
                document_id,
                i,
                chunk.text,
                chunk.page_no,
                chunk.section_path,
                item.language,
                crop_id,
                item.state,
                _vector_literal(embeddings[i]) if embeddings is not None else None,
                token_counts[i] if token_counts else None,
            )
        )

    async with conn.transaction():
        await conn.execute(
            "delete from public.chunks where document_id = $1", document_id
        )
        await conn.executemany(
            """
            insert into public.chunks (
                document_id, chunk_index, content, page_no, section_path,
                language, crop_id, state, embedding, token_count
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9::extensions.vector, $10)
            """,
            rows,
        )
    return len(rows)
