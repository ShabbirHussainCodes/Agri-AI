"""Phase 3 ingestion: approved PDFs -> chunks in Postgres.

Runs on the developer laptop only (Docling needs ~6 GB RAM). Reads
ingest/sources.yaml, so a document that has not been licence-checked and
approved cannot be ingested by accident.

    cd ingest
    python run.py --dry-run           # parse + chunk, print a summary, touch nothing
    python run.py --dry-run --dump    # ...and write the chunks out for eyeballing
    python run.py                     # full run: parse, chunk, embed, write to Postgres
    python run.py --handle 10568/180614
"""
import argparse
import asyncio
import hashlib
import re
import sys
from pathlib import Path

import asyncpg
import numpy as np
from pypdf import PdfReader

from config import INGEST_DIR, settings
from db import replace_chunks, resolve_crop_id, upsert_document
from embed import E5Embedder
from parse_chunk import (
    ParsedChunk,
    build_chunker,
    build_converter,
    chunk_document,
    parse_pdf,
)
from sources import ApprovedItem, load_approved_items

EMBED_BATCH = 16

# Chunks shorter than this are page furniture, not knowledge: journal labels
# ("Article"), running heads, stray captions. They can never answer a farmer's
# question, but they can win a retrieval slot from something that could.
# Dropped chunks are always printed -- nothing disappears silently.
MIN_CHUNK_TOKENS = 15

# Signatures of PDF text-extraction damage, not of bad writing.
#
# GLUED_CASE: a lowercase run running straight into capitals, e.g. "ltithEG",
#   "ttIPDM", "biAcross", "plantsThe" -- characters were dropped between two
#   words and the remains fused.
# CONSONANT_BLOB: an all-lowercase word of 4+ letters with no vowel at all,
#   e.g. "ttkftd", "gpgpp", "bflld". Restricted to lowercase so acronyms
#   (IPDM, TNAU, SDGs) are never caught, and anchored on word boundaries so
#   ordinary English consonant clusters ("months", "strength") are not either.
#
# Measured on 183 chunks across both Phase 3 documents and both backends:
# zero false positives once the URL words below are excluded, and it caught
# exactly the 4 pypdfium chunks that are visibly broken. One hit is enough to
# drop a chunk -- garbled evidence is worse than missing evidence.
GLUED_CASE = re.compile(r"[a-z]{2,}[A-Z]{2,}|[a-z]{3,}[A-Z][a-z]{3,}")
CONSONANT_BLOB = re.compile(r"\b[bcdfghjklmnpqrstvwxyz]{4,}\b")
GARBLE_ALLOWLIST = {"https", "html", "www", "ftp", "xml", "json"}


def find_garble(text: str) -> list[str]:
    """Extraction-damage tokens in a chunk, or [] if it looks intact."""
    hits = GLUED_CASE.findall(text)
    hits += [w for w in CONSONANT_BLOB.findall(text) if w not in GARBLE_ALLOWLIST]
    return hits


def screen_chunks(
    chunks: list[ParsedChunk], embedder: E5Embedder
) -> tuple[list[tuple[ParsedChunk, int]], list[tuple[ParsedChunk, int, str]]]:
    """Split chunks into (kept, dropped-with-reason).

    Two reasons a chunk never reaches the corpus:
      too-short  -- page furniture ("Article", running heads) that can never
                    answer a question but can still win a retrieval slot.
      garbled    -- the text extractor mangled it (see find_garble). Better to
                    lose the passage than to let the agent quote nonsense as
                    evidence.
    Everything dropped is reported by the caller; nothing disappears silently.
    """
    kept: list[tuple[ParsedChunk, int]] = []
    dropped: list[tuple[ParsedChunk, int, str]] = []

    for chunk in chunks:
        n_tokens = embedder.count_tokens(chunk.text)
        if n_tokens < MIN_CHUNK_TOKENS:
            dropped.append((chunk, n_tokens, f"too short (< {MIN_CHUNK_TOKENS} tokens)"))
            continue
        garble = find_garble(chunk.text)
        if garble:
            sample = ", ".join(dict.fromkeys(garble))[:80]
            dropped.append((chunk, n_tokens, f"garbled extraction: {sample}"))
            continue
        kept.append((chunk, n_tokens))

    return kept, dropped


DUMP_DIR = INGEST_DIR / "_cache" / "dumps"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pdf_page_count(path: Path) -> int | None:
    try:
        return len(PdfReader(str(path)).pages)
    except Exception as exc:  # noqa: BLE001 -- page count is metadata, not critical
        print(f"  ! could not read page count ({exc})")
        return None


def embed_chunks(embedder: E5Embedder, texts: list[str]) -> np.ndarray:
    """Batched so a long document does not build one huge ONNX input tensor."""
    batches = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        batches.append(embedder.embed_passages(batch))
        print(f"  embedded {min(start + EMBED_BATCH, len(texts))}/{len(texts)}")
    return np.vstack(batches)


def write_dump(
    item: ApprovedItem,
    kept: list[tuple[ParsedChunk, int]],
    dropped: list[tuple[ParsedChunk, int, str]],
) -> Path:
    """Write every chunk to a text file so a human can actually read what
    Docling extracted -- especially tables, which is the one thing the summary
    counts cannot tell us."""
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    # The OCR mode is in the filename so an ocr-on and an ocr-off run can sit
    # side by side and be diffed, instead of one silently overwriting the other.
    mode = "ocr-on" if settings.docling_ocr else "ocr-off"
    path = (
        DUMP_DIR
        / f"{item.handle.replace('/', '-')}_chunks_{mode}_{settings.docling_backend}.txt"
    )

    with path.open("w", encoding="utf-8") as out:
        out.write(f"{item.handle} -- {item.title}\n")
        out.write(f"{item.item_url}\n")
        out.write(f"kept {len(kept)} chunks, dropped {len(dropped)}\n")
        out.write("=" * 78 + "\n\n")

        for i, (chunk, n_tokens) in enumerate(kept):
            out.write(f"--- chunk {i} | page {chunk.page_no} | {n_tokens} tokens\n")
            out.write(f"    section: {chunk.section_path}\n")
            # Confirms contextualisation actually happened: this line should
            # start with the heading trail, not with the body text.
            out.write(f"    embed_text starts: {chunk.embed_text[:160]!r}\n\n")
            out.write(chunk.text + "\n\n")

        if dropped:
            out.write("=" * 78 + "\nDROPPED\n" + "=" * 78 + "\n")
            for chunk, n_tokens, reason in dropped:
                out.write(f"[page {chunk.page_no}, {n_tokens} tokens] {reason}\n")
                out.write(f"    {chunk.text!r}\n\n")

    return path


async def ingest_item(
    item: ApprovedItem,
    embedder: E5Embedder,
    chunker,
    converter,
    conn: asyncpg.Connection | None,
    dump: bool = False,
) -> None:
    print(f"\n=== {item.handle} -- {item.title[:70]}")
    print(f"  licence: {item.licence} | doc_type: {item.doc_type} | lang: {item.language}")

    sha = file_sha256(item.local_path)
    pages = pdf_page_count(item.local_path)
    print(f"  sha256: {sha[:16]}...  pages: {pages}")

    print("  parsing with Docling (slow) ...")
    doc = parse_pdf(converter, item.local_path)

    all_chunks = chunk_document(doc, chunker)
    if not all_chunks:
        print("  ! produced 0 chunks -- skipping")
        return

    kept, dropped = screen_chunks(all_chunks, embedder)
    if dropped:
        print(f"  dropped {len(dropped)} chunk(s):")
        for chunk, n_tokens, reason in dropped:
            preview = " ".join(chunk.text.split())[:55]
            print(f"    - page {chunk.page_no}, {n_tokens} tok [{reason}]: {preview!r}")

    if not kept:
        print("  ! every chunk was screened out -- skipping")
        return

    chunks = [c for c, _ in kept]
    token_counts = [n for _, n in kept]

    with_page = sum(1 for c in chunks if c.page_no is not None)
    with_section = sum(1 for c in chunks if c.section_path)
    contextualised = sum(1 for c in chunks if c.embed_text != c.text)
    print(
        f"  chunks kept: {len(chunks)} | with page_no: {with_page} | "
        f"with section_path: {with_section} | contextualised: {contextualised}"
    )
    print(
        f"  tokens/chunk: min {min(token_counts)}, "
        f"median {sorted(token_counts)[len(token_counts) // 2]}, "
        f"max {max(token_counts)}"
    )

    # rag-design.md section 6 depends on page numbers to build citations, so a
    # run that produced none is a real problem, not a cosmetic one.
    if with_page == 0:
        print("  ! WARNING: no chunk carried a page number -- citations cannot")
        print("    be built from this document. Run probe.py before trusting it.")

    # If contextualisation silently stopped working, embeddings quietly get
    # worse and nothing else complains -- so say it loudly here.
    if contextualised == 0:
        print("  ! WARNING: no chunk was contextualised (embed_text == text).")
        print("    Heading context is missing from every embedding.")

    if dump:
        path = write_dump(item, kept, dropped)
        print(f"  dumped chunks to {path}")

    if conn is None:
        print("  [dry run] nothing written")
        return

    embeddings = embed_chunks(embedder, [c.embed_text for c in chunks])

    crop_id = await resolve_crop_id(conn, item.crop_name)
    document_id = await upsert_document(conn, item, sha, pages)
    written = await replace_chunks(
        conn, document_id, item, chunks, embeddings, crop_id, token_counts
    )
    print(f"  wrote {written} chunks (document {document_id})")


async def main_async(args: argparse.Namespace) -> int:
    items = load_approved_items()
    if args.handle:
        items = [i for i in items if i.handle == args.handle]
        if not items:
            print(f"No approved item with handle {args.handle!r}")
            return 1

    print(f"{len(items)} approved item(s) to ingest")

    print(
        f"Docling OCR: {'ON' if settings.docling_ocr else 'OFF'} | "
        f"backend: {settings.docling_backend}"
    )

    embedder = E5Embedder(cache_dir=settings.embed_cache_dir)
    chunker = build_chunker(embedder.tokenizer, settings.chunk_max_tokens)
    converter = build_converter(settings.docling_ocr, settings.docling_backend)

    conn = None
    if not args.dry_run:
        if not settings.database_url:
            print(
                "AGRIAI_DATABASE_URL is not set. Set it in .env (point it at the "
                "local Supabase stack first), or use --dry-run to parse and "
                "chunk without a database."
            )
            return 1
        conn = await asyncpg.connect(settings.database_url)
    try:
        for item in items:
            await ingest_item(
                item, embedder, chunker, converter, conn, dump=args.dump
            )
    finally:
        if conn is not None:
            await conn.close()

    print("\nDone.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AgriAI corpus ingestion (Phase 3)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and chunk only; do not embed or write to the database",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help=f"write every chunk to {DUMP_DIR} for human review (gitignored)",
    )
    parser.add_argument("--handle", help="ingest only this repository handle")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
