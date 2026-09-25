"""Guards the one real risk of keeping two e5 embedders (Phase 4 decision:
API copy + parity test): ingest/embed.py embeds the corpus, app/retrieval/
embedder.py embeds questions. If they ever disagree, cosine similarity still
returns numbers -- just meaningless ones -- and retrieval degrades silently.

The model tests load the real ~470 MB ONNX model (from the ingest cache if it
is already there; otherwise it downloads once). No database needed.
"""
import importlib.util
import sys

import numpy as np
import pytest

from app.core.config import REPO_ROOT, settings
from app.retrieval.embedder import EMBED_DIM, QueryEmbedder, to_pgvector_literal

# English, Hindi (Devanagari), and Hinglish -- the three ways farmers ask.
QUERIES = [
    "Which eggplant rootstock performed best with IPDM in the tomato trial?",
    "टमाटर में जीवाणु म्लानि रोग से कैसे बचें?",
    "gehun ko paani kab dena chahiye",
]


def _load_ingest_embedder_class():
    path = REPO_ROOT / "ingest" / "embed.py"
    spec = importlib.util.spec_from_file_location("agriai_ingest_embed", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.E5Embedder


@pytest.fixture(scope="module")
def both_embedders():
    ingest_cls = _load_ingest_embedder_class()
    return ingest_cls(settings.embed_cache_dir), QueryEmbedder(settings.embed_cache_dir)


@pytest.mark.parametrize("query", QUERIES)
def test_api_and_ingest_embed_queries_identically(both_embedders, query):
    ingest_emb, api_emb = both_embedders
    expected = np.asarray(ingest_emb.embed_query(query), dtype=np.float32)
    actual = api_emb.embed_query(query)
    np.testing.assert_allclose(actual, expected, atol=1e-6)


@pytest.mark.parametrize("query", QUERIES)
def test_query_vectors_are_384d_and_unit_length(both_embedders, query):
    _, api_emb = both_embedders
    vec = api_emb.embed_query(query)
    assert vec.shape == (EMBED_DIM,)
    assert float(np.linalg.norm(vec)) == pytest.approx(1.0, abs=1e-5)


def test_pgvector_literal_round_trips_exactly():
    vec = np.array([0.1, -0.25, 1e-8, 0.3333333], dtype=np.float32)
    literal = to_pgvector_literal(vec)
    assert literal.startswith("[") and literal.endswith("]")
    parsed = np.array([float(x) for x in literal[1:-1].split(",")], dtype=np.float32)
    np.testing.assert_array_equal(parsed, vec)
