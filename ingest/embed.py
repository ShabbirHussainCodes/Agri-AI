"""Local ONNX embeddings -- multilingual-e5-small (CLAUDE.md stack table).

Runs on CPU, offline after the first download, and costs nothing per call --
which is the whole reason the embedder is local while the LLM is not.

TWO THINGS THAT SILENTLY BREAK e5 IF GOT WRONG, so they live here rather than
at any call site:
  1. Prefixes. e5 was trained with "passage: " on documents and "query: " on
     questions. Embedding both sides the same way still "works" -- it just
     retrieves noticeably worse, with nothing in the logs to show for it.
  2. Pooling. e5 uses *mean* pooling over the last hidden state, masked by
     attention, then L2 normalisation. Taking the CLS token instead is a
     common copy-paste bug and produces plausible-looking, wrong vectors.

L2-normalised vectors are why the HNSW index in the corpus migration uses
cosine distance.
"""
from pathlib import Path

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer

MODEL_REPO = "intfloat/multilingual-e5-small"

# fp32 export, ~470 MB, a single self-contained file (no external .onnx_data).
# The repo also ships model_qint8_avx512_vnni.onnx (~118 MB), which is ~4x
# smaller but needs an AVX512-VNNI x86 CPU -- useless on an Apple-silicon
# laptop. Revisit it for the deployed API host in Phase 4, not here.
ONNX_FILENAME = "onnx/model.onnx"

EMBED_DIM = 384
MAX_LENGTH = 512


class E5Embedder:
    def __init__(self, cache_dir: Path, max_length: int = MAX_LENGTH):
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_path = hf_hub_download(
            repo_id=MODEL_REPO, filename=ONNX_FILENAME, cache_dir=str(cache_dir)
        )
        self.session = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"]
        )
        # XLM-R based models take input_ids + attention_mask; some exports also
        # declare token_type_ids. Feed exactly what this graph asks for instead
        # of assuming a fixed set.
        self._input_names = {i.name for i in self.session.get_inputs()}
        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_REPO, cache_dir=str(cache_dir)
        )
        self.max_length = max_length

    def _encode(self, texts: list[str]) -> np.ndarray:
        enc = self.tokenizer(
            texts,
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
                # This ONNX export declares token_type_ids as a REQUIRED input,
                # but multilingual-e5-small is XLM-RoBERTa based and its
                # tokenizer never emits them. XLM-R has type_vocab_size=1, so
                # every token is segment 0 -- feeding zeros is exactly what the
                # model would have used. (Verified on the real graph: inputs
                # are input_ids, attention_mask, token_type_ids.)
                feed[name] = np.zeros_like(enc["input_ids"])
            else:
                raise RuntimeError(
                    f"ONNX graph requires input {name!r}, which the tokenizer "
                    "does not produce and this code does not know how to build."
                )

        last_hidden = self.session.run(None, feed)[0]

        mask = enc["attention_mask"][..., None].astype(last_hidden.dtype)
        summed = (last_hidden * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), 1e-9, None)
        pooled = summed / counts

        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return pooled / np.clip(norms, 1e-12, None)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        """Not used by ingestion -- kept here so Phase 4's retriever cannot
        accidentally embed queries with a different prefix or pooling."""
        return self._encode([f"query: {text}"])[0]

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=True))
