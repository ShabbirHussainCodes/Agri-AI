"""Query-side embedder: multilingual-e5-small via local ONNX.

WHY A SECOND COPY OF THE EMBEDDER EXISTS (decision, Phase 4, 2026-09-25):
ingest/embed.py embeds *passages* on the developer laptop; this module embeds
*queries* inside the API process. The two deployables are kept independent --
ingest drags in Docling (~6 GB RAM) and must never be installed with the API
(ingest/README.md) -- so the API cannot simply import ingest/.

The cost of that independence is that two copies of the same maths could
drift apart. If they ever did, retrieval would silently get worse with
nothing in the logs: a query vector and a passage vector from slightly
different pipelines still produce a cosine similarity, just a meaningless
one. tests/test_embedder_parity.py is the guard: it embeds the same queries
through BOTH implementations and fails if the vectors differ.

The two things that silently break e5 (see ingest/embed.py for the full
explanation) are therefore identical here on purpose:
  1. the "query: " prefix (passages were embedded with "passage: "),
  2. attention-masked MEAN pooling + L2 normalisation (not the CLS token).
Pinned library versions in requirements.txt match ingest/requirements.lock.txt
for the same reason.
"""
from pathlib import Path
from threading import Lock

import numpy as np

MODEL_REPO = "intfloat/multilingual-e5-small"
# Same file ingest uses (fp32, ~470 MB). The int8 AVX512-VNNI export is a
# deployment-host question for later, not a Phase 4 one (ingest/embed.py).
ONNX_FILENAME = "onnx/model.onnx"
EMBED_DIM = 384
MAX_LENGTH = 512


class QueryEmbedder:
    def __init__(self, cache_dir: Path, max_length: int = MAX_LENGTH):
        # Imported here, not at module top: the model is ~470 MB and these
        # libraries are heavy. Anything that only needs the *types* in this
        # package (fusion, tests with a fake embedder) should not pay for it.
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from transformers import AutoTokenizer

        cache_dir.mkdir(parents=True, exist_ok=True)
        model_path = hf_hub_download(
            repo_id=MODEL_REPO, filename=ONNX_FILENAME, cache_dir=str(cache_dir)
        )
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self.session.get_inputs()}
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_REPO, cache_dir=str(cache_dir))
        self.max_length = max_length

    def embed_query(self, text: str) -> np.ndarray:
        """Returns one L2-normalised float32 vector of length EMBED_DIM."""
        enc = self.tokenizer(
            [f"query: {text}"],
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="np",
        )
        feed = {}
        for name in self._input_names:
            if name in enc:
                feed[name] = enc[name]
            elif name == "token_type_ids":
                # The ONNX export requires it; XLM-R never emits it and has
                # type_vocab_size=1, so zeros are exactly right (ingest/embed.py).
                feed[name] = np.zeros_like(enc["input_ids"])
            else:
                raise RuntimeError(f"ONNX graph requires unknown input {name!r}")

        last_hidden = self.session.run(None, feed)[0]
        mask = enc["attention_mask"][..., None].astype(last_hidden.dtype)
        pooled = (last_hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
        vec = pooled[0]
        vec = vec / max(float(np.linalg.norm(vec)), 1e-12)
        if vec.shape != (EMBED_DIM,):
            raise RuntimeError(f"expected a {EMBED_DIM}-d vector, got {vec.shape}")
        return vec.astype(np.float32)


_embedder: QueryEmbedder | None = None
_lock = Lock()


def get_query_embedder() -> QueryEmbedder:
    """Process-wide singleton, created on first use. Loading the ONNX session
    takes seconds; doing it per request would dominate /ask latency. A lock,
    because two concurrent first requests must not both load a 470 MB model."""
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                from app.core.config import settings

                _embedder = QueryEmbedder(settings.embed_cache_dir)
    return _embedder


def to_pgvector_literal(vec: np.ndarray) -> str:
    """asyncpg has no codec for pgvector's type, so the vector is sent as its
    text form '[x1,x2,...]' and cast with ::extensions.vector in SQL.
    repr-precision floats: a shortened literal would change the vector."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
