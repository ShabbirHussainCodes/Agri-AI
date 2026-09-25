"""Integration tests for hybrid retrieval (app/retrieval/hybrid.py).

Needs the local Supabase stack (`supabase start`) WITH the Phase 3 corpus
ingested (113 chunks -- run ingest/verify_corpus.py first if unsure), plus
the embedder model. Queries run as the `authenticated` role, the same role
/ask uses, so these also prove the corpus grants are sufficient.

Assertions are about behaviour that follows from the corpus content and the
algorithm (exact terms found by the lexical leg, cascade widening, ordering),
never about exact rankings -- those are what the eval baseline measures.
"""
import asyncpg
import pytest
import pytest_asyncio

from app.core.config import settings
from app.retrieval.embedder import QueryEmbedder
from app.retrieval.hybrid import retrieve

pytestmark = pytest.mark.asyncio

# 0.0 accepts any tier that returns a dense hit. The real threshold is
# calibrated on the eval set in Phase 4 step 5; these tests are about
# mechanics, not about where that line sits.
ACCEPT_ANYTHING = 0.0


@pytest.fixture(scope="module")
def embedder():
    return QueryEmbedder(settings.embed_cache_dir)


@pytest_asyncio.fixture
async def conn():
    c = await asyncpg.connect(settings.database_url)
    tr = c.transaction()
    await tr.start()
    await c.execute("set local role authenticated")
    try:
        yield c
    finally:
        await tr.rollback()
        await c.close()


async def test_lexical_leg_finds_exact_accession_names(conn, embedder):
    # "EG 203" is an accession code -- exactly the kind of token embeddings
    # blur and full-text search matches literally (rag-design.md section 3).
    result = await retrieve(conn, embedder, "EG 203 and TS 03 rootstock", min_similarity=ACCEPT_ANYTHING)
    assert any(c.lexical_rank is not None and "EG 203" in c.content for c in result.chunks)


async def test_results_are_fused_ordered_and_carry_provenance(conn, embedder):
    result = await retrieve(conn, embedder, "How much rainfall does Mandla receive?", min_similarity=ACCEPT_ANYTHING, top_k=10)
    assert result.accepted and result.tier == "unfiltered"
    assert 0 < len(result.chunks) <= 10
    scores = [c.rrf_score for c in result.chunks]
    assert scores == sorted(scores, reverse=True)
    for c in result.chunks:
        assert c.licence and c.url and c.doc_title
        assert c.dense_rank is not None or c.lexical_rank is not None


async def test_hindi_query_is_served_by_the_dense_leg(conn, embedder):
    # Corpus is English-only; a Devanagari query shares no lexemes with it,
    # so any hit must come from the multilingual dense leg (ADR-0007).
    result = await retrieve(conn, embedder, "टमाटर की कलम बांधने में कौन सा रूटस्टॉक अच्छा रहा?", min_similarity=ACCEPT_ANYTHING)
    assert result.chunks
    assert all(c.dense_rank is not None for c in result.chunks)


async def test_cascade_widens_when_the_crop_has_no_corpus_chunks(conn, embedder):
    crop_without_chunks = await conn.fetchval(
        "select id from public.crops where id not in "
        "(select crop_id from public.chunks where crop_id is not null) limit 1"
    )
    assert crop_without_chunks is not None, "seed data has no crop without corpus chunks"
    result = await retrieve(conn, embedder, "rainfall in Mandla", min_similarity=ACCEPT_ANYTHING, crop_id=crop_without_chunks, state="Madhya Pradesh")
    assert result.tier == "unfiltered"
    assert result.accepted


async def test_unreachable_threshold_returns_widest_tier_not_accepted(conn, embedder):
    result = await retrieve(conn, embedder, "rainfall in Mandla", min_similarity=1.01)
    assert result.tier == "unfiltered"
    assert result.accepted is False
    assert result.chunks  # evidence is still returned; the CALLER decides to abstain


async def test_empty_query_is_rejected(conn, embedder):
    with pytest.raises(ValueError):
        await retrieve(conn, embedder, "   ", min_similarity=ACCEPT_ANYTHING)
