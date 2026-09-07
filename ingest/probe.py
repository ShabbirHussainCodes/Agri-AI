"""One-off inspection script: prints what the INSTALLED versions of Docling
and the embedder actually give us, before the real pipeline depends on it.

CLAUDE.md section 11 keeps a list of "things to verify before they harden".
This is that check for Phase 3: chunk metadata attribute names, whether page
numbers and headings really come through, and the embedding shape/norm.

    cd ingest && python probe.py
"""
import sys

from config import settings
from embed import E5Embedder
from parse_chunk import build_chunker, build_converter, parse_pdf
from sources import load_approved_items


def main() -> int:
    items = load_approved_items()
    if not items:
        print("No approved items in sources.yaml.")
        return 1

    item = items[0]
    print(f"Probing: {item.handle} -- {item.title}")
    print(f"File:    {item.local_path}\n")

    import docling

    print(f"docling version: {getattr(docling, '__version__', 'unknown')}")

    embedder = E5Embedder(cache_dir=settings.embed_cache_dir)
    print(f"onnx inputs:     {sorted(embedder._input_names)}")

    chunker = build_chunker(embedder.tokenizer, settings.chunk_max_tokens)
    print(f"chunker:         {type(chunker).__name__}")
    print(f"docling OCR:     {'ON' if settings.docling_ocr else 'OFF'}")
    print(f"docling backend: {settings.docling_backend}\n")

    converter = build_converter(settings.docling_ocr, settings.docling_backend)
    doc = parse_pdf(converter, item.local_path)
    raw_chunks = list(chunker.chunk(dl_doc=doc))
    print(f"chunks produced: {len(raw_chunks)}\n")

    first = raw_chunks[0]
    print("--- first chunk: object shape ---")
    print(f"type: {type(first)}")
    print(f"attrs: {[a for a in dir(first) if not a.startswith('_')]}")
    meta = getattr(first, "meta", None)
    print(f"meta type: {type(meta)}")
    print(f"meta attrs: {[a for a in dir(meta) if not a.startswith('_')]}")
    print(f"headings: {getattr(meta, 'headings', None)}")

    doc_items = getattr(meta, "doc_items", None) or []
    if doc_items:
        prov = getattr(doc_items[0], "prov", None) or []
        print(f"first doc_item prov: {prov[:1]}")

    print("\n--- first chunk: text (first 400 chars) ---")
    print(first.text[:400])

    # Contextualisation check: this should come back with the heading trail in
    # front of the body text. If it comes back identical to first.text, every
    # embedding is losing its heading context (rag-design.md section 5).
    contextualize = getattr(chunker, "contextualize", None)
    print("\n--- contextualize() ---")
    if callable(contextualize):
        ctx = str(contextualize(first))
        print(f"differs from raw text: {ctx != first.text}")
        print(ctx[:400])
    else:
        print("chunker has no contextualize() -- parse_chunk.py will fall back")

    vecs = embedder.embed_passages([first.text])
    print(f"\nembedding shape: {vecs.shape}  (expected (1, 384))")
    print(f"embedding L2 norm: {float((vecs[0] ** 2).sum()) ** 0.5:.6f}  (expected ~1.0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
