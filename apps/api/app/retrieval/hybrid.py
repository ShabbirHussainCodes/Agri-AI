"""Hybrid retrieval over public.chunks: dense leg + lexical leg, fused with
RRF, behind a metadata widening cascade (docs/rag/rag-design.md sections 1, 3, 4).

Deterministic, not an LLM tool (Phase 4 decision, 2026-09-25): run_agent()
calls retrieve() for every question, the same way it calls get_farm_context.
An LLM-gated search tool would add a failure mode ("the model never searched")
that the eval could not tell apart from "retrieval found nothing".

Reads through whatever connection it is given. In /ask that is the
RLS-scoped `authenticated` connection; the corpus tables grant SELECT to
`authenticated` (corpus migration), so no new access path is created.
"""
from typing import Protocol, Sequence
from uuid import UUID

import asyncpg
import numpy as np
from pydantic import BaseModel, ConfigDict

from app.retrieval.embedder import to_pgvector_literal
from app.retrieval.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion

DENSE = "dense"
LEXICAL = "lexical"


class Embedder(Protocol):
    """Anything with embed_query -- the real QueryEmbedder, or a fake in tests."""

    def embed_query(self, text: str) -> np.ndarray: ...


class RetrievalTier(BaseModel):
    """One step of the widening cascade (rag-design.md section 4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str  # "crop+state" | "crop" | "unfiltered"
    crop_id: UUID | None = None
    state: str | None = None


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    document_id: UUID
    handle: str | None
    doc_title: str
    publisher: str | None
    published_year: int | None
    doc_type: str
    licence: str
    url: str
    page_no: int | None
    section_path: str | None
    language: str
    content: str
    # Evaluation/debug signals -- which leg found it, and how strongly.
    dense_similarity: float | None
    dense_rank: int | None
    lexical_rank: int | None
    rrf_score: float


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    # Which cascade tier produced these chunks. Passed to the model so an
    # answer can say "no crop-specific guidance found; this is general".
    tier: str
    # Did that tier clear the relevance bar, or is it the last-resort fallback?
    accepted: bool
    # Best cosine similarity of the dense leg in this tier. This one number is
    # both the cascade's acceptance test and the abstention floor's input.
    top_dense_similarity: float | None
    chunks: list[RetrievedChunk]


def build_tiers(crop_id: UUID | None, state: str | None) -> list[RetrievalTier]:
    """exact (crop+state) -> drop state -> drop crop (rag-design.md section 4).

    The last tier is "unfiltered" (the whole corpus), not a "national" tier:
    no chunk carries a national/generic flag yet, and naming a tier after
    metadata that does not exist would be a false claim.
    """
    tiers: list[RetrievalTier] = []
    if crop_id is not None and state:
        tiers.append(RetrievalTier(name="crop+state", crop_id=crop_id, state=state))
    if crop_id is not None:
        tiers.append(RetrievalTier(name="crop", crop_id=crop_id))
    tiers.append(RetrievalTier(name="unfiltered"))
    return tiers


# Dense leg. The operator and type are schema-qualified because pgvector
# lives in the `extensions` schema (migration 20260830090000); relying on
# search_path would work until someone changes a role's search_path.
#
# Caveat worth knowing: with a WHERE filter, HNSW applies the filter AFTER
# its approximate search, so a narrow filter can return fewer rows than
# LIMIT. Harmless at 113 chunks; revisit if the corpus grows by 100x.
_DENSE_SQL = """
select c.id,
       1 - (c.embedding operator(extensions.<=>) $1::extensions.vector) as similarity
from public.chunks c
where c.embedding is not null
  and ($2::uuid is null or c.crop_id = $2)
  and ($3::text is null or c.state = $3)
order by c.embedding operator(extensions.<=>) $1::extensions.vector, c.id
limit $4
"""

# Lexical leg.
#
# plainto_tsquery() ANDs every word ('eg' & '203' & 'rootstock' & ...). A
# farmer's full question almost never has ALL its words in one chunk, so an
# AND query returns nothing for most natural questions. Replacing ' & ' with
# ' | ' turns it into an OR query, and ts_rank_cd then rewards chunks that
# cover more of the terms, closer together.
#
# The rewritten text is cast straight to ::tsquery (not re-run through
# to_tsquery) so the lexemes are not stemmed a second time.
#
# Hindi rows are indexed with the 'simple' config (no Hindi stemmer ships
# with Postgres -- rag-design.md section 3), so they are matched with a
# 'simple' query; everything else with 'english'. nullif(): a question made
# only of stopwords yields an empty query, which must match nothing rather
# than raise.
_LEXICAL_SQL = """
with q as (
  select nullif(replace(plainto_tsquery('english', $1)::text, ' & ', ' | '), '')::tsquery as en,
         nullif(replace(plainto_tsquery('simple',  $1)::text, ' & ', ' | '), '')::tsquery as si
)
select c.id,
       ts_rank_cd(c.tsv, case when c.language = 'hi' then q.si else q.en end) as rank
from public.chunks c cross join q
where c.tsv @@ (case when c.language = 'hi' then q.si else q.en end)
  and ($2::uuid is null or c.crop_id = $2)
  and ($3::text is null or c.state = $3)
order by rank desc, c.id
limit $4
"""

_DETAILS_SQL = """
select c.id, c.document_id, c.content, c.page_no, c.section_path, c.language,
       d.handle, d.title, d.publisher, d.published_year, d.doc_type, d.licence, d.url
from public.chunks c
join public.documents d on d.id = c.document_id
where c.id = any($1::uuid[])
"""


async def _retrieve_tier(
    conn: asyncpg.Connection,
    query: str,
    query_vec_literal: str,
    tier: RetrievalTier,
    *,
    top_k: int,
    leg_limit: int,
    rrf_k: int,
) -> RetrievalResult:
    dense_rows = await conn.fetch(
        _DENSE_SQL, query_vec_literal, tier.crop_id, tier.state, leg_limit
    )
    lexical_rows = await conn.fetch(
        _LEXICAL_SQL, query, tier.crop_id, tier.state, leg_limit
    )

    similarity = {r["id"]: float(r["similarity"]) for r in dense_rows}
    fused = reciprocal_rank_fusion(
        {DENSE: [r["id"] for r in dense_rows], LEXICAL: [r["id"] for r in lexical_rows]},
        k=rrf_k,
    )[:top_k]

    details = {}
    if fused:
        rows = await conn.fetch(_DETAILS_SQL, [item.key for item in fused])
        details = {r["id"]: r for r in rows}

    chunks = [
        RetrievedChunk(
            chunk_id=item.key,
            document_id=details[item.key]["document_id"],
            handle=details[item.key]["handle"],
            doc_title=details[item.key]["title"],
            publisher=details[item.key]["publisher"],
            published_year=details[item.key]["published_year"],
            doc_type=details[item.key]["doc_type"],
            licence=details[item.key]["licence"],
            url=details[item.key]["url"],
            page_no=details[item.key]["page_no"],
            section_path=details[item.key]["section_path"],
            language=details[item.key]["language"],
            content=details[item.key]["content"],
            dense_similarity=similarity.get(item.key),
            dense_rank=item.ranks.get(DENSE),
            lexical_rank=item.ranks.get(LEXICAL),
            rrf_score=item.score,
        )
        for item in fused
        if item.key in details
    ]

    return RetrievalResult(
        query=query,
        tier=tier.name,
        accepted=False,  # decided by the caller, which knows the threshold
        top_dense_similarity=max(similarity.values()) if similarity else None,
        chunks=chunks,
    )


async def retrieve(
    conn: asyncpg.Connection,
    embedder: Embedder,
    query: str,
    *,
    min_similarity: float,
    crop_id: UUID | None = None,
    state: str | None = None,
    top_k: int = 20,
    leg_limit: int = 40,
    rrf_k: int = DEFAULT_RRF_K,
) -> RetrievalResult:
    """Walk the cascade from narrowest to widest and return the first tier
    whose best dense match reaches `min_similarity`.

    Why the acceptance test is relevance, not "got at least N rows": the dense
    leg ALWAYS returns rows (nearest neighbours exist even when nothing is
    relevant). A row-count test would accept a crop tier full of unrelated
    tomato chunks for a question about Mandla rainfall and never widen.

    `min_similarity` has no default on purpose: it is calibrated on the eval
    set (Phase 4 step 5), and a guessed default would be an unexplained magic
    number. If no tier reaches it, the widest tier is returned with
    accepted=False and the caller decides (abstain, or proceed without
    corpus evidence).
    """
    if not query.strip():
        raise ValueError("query must not be empty")

    vec_literal = to_pgvector_literal(embedder.embed_query(query))
    result: RetrievalResult | None = None
    for tier in build_tiers(crop_id, state):
        result = await _retrieve_tier(
            conn, query, vec_literal, tier, top_k=top_k, leg_limit=leg_limit, rrf_k=rrf_k
        )
        if result.top_dense_similarity is not None and result.top_dense_similarity >= min_similarity:
            return result.model_copy(update={"accepted": True})

    assert result is not None  # build_tiers always yields the unfiltered tier
    return result


def gold_hit_rank(chunks: Sequence[RetrievedChunk], handle: str, page: int) -> int | None:
    """1-based rank of the first chunk from the gold (handle, page), or None.
    Used by the eval runner; lives here so the definition of a 'hit' is next
    to the data it inspects."""
    for rank, c in enumerate(chunks, start=1):
        if c.handle == handle and c.page_no == page:
            return rank
    return None
