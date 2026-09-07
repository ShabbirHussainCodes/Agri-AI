"""Docling parse + structure-aware chunking.

Why Docling's chunker instead of a hand-rolled recursive splitter:
rag-design.md section 4 requires every chunk to carry `page_no` and
`section_path`. Those come from Docling's own layout model (which headings a
text block sits under, which page it was printed on). A plain character/token
splitter over `export_to_markdown()` throws that provenance away, and without
page numbers the citation story in rag-design.md section 6 cannot work.

See the "chunking" note in the Phase 3 summary: this is a deviation from
rag-design.md section 5's wording ("recursive/fixed chunking, 15% overlap")
and needs Shabbir's sign-off before it is committed.
"""
from dataclasses import dataclass
from pathlib import Path

from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption


@dataclass(frozen=True)
class ParsedChunk:
    # Raw chunk text. This is what gets stored in chunks.content and shown to
    # the LLM / quoted in a citation.
    text: str

    # The SAME chunk with its heading trail prepended, via Docling's
    # contextualize(). Only ever embedded, never stored or displayed.
    #
    # Why the two differ: a chunk reading "apply at 15 days after
    # transplanting" carries no clue that it is about tomato. Embedding the
    # bare text makes it unretrievable for "tomato spray timing" -- the
    # orphaned-chunk problem in rag-design.md section 5. Prepending the
    # headings puts that context into the vector without polluting the text we
    # later show as evidence.
    embed_text: str

    page_no: int | None
    section_path: str | None


# name -> backend class. "default" is absent on purpose: leaving `backend`
# unset lets PdfFormatOption keep its own default (currently
# ThreadedDoclingParseDocumentBackend), so we never pin a default that a
# Docling upgrade has since moved on from.
BACKENDS = {
    "pypdfium": PyPdfiumDocumentBackend,
    "parse-v4": DoclingParseV4DocumentBackend,
}


def build_converter(do_ocr: bool, backend: str = "default") -> DocumentConverter:
    """One converter, reused for every document -- it loads layout and table
    models on construction, so building it per PDF wastes that work.

    do_ocr is deliberately a caller decision: for a digital-native PDF, OCR
    competes with the embedded text layer instead of helping it (see the note
    on `docling_ocr` in config.py). Table structure stays ON either way --
    that is what gives us the crop calendar and the treatment tables at all.

    backend selects the text-extraction engine; see `docling_backend` in
    config.py for why that is a knob at all.
    """
    if backend != "default" and backend not in BACKENDS:
        raise ValueError(
            f"unknown docling backend {backend!r}; "
            f"expected 'default' or one of {sorted(BACKENDS)}"
        )

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = do_ocr
    pipeline_options.do_table_structure = True

    kwargs = {"pipeline_options": pipeline_options}
    if backend in BACKENDS:
        kwargs["backend"] = BACKENDS[backend]

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(**kwargs)}
    )


def parse_pdf(converter: DocumentConverter, path: Path):
    """PDF -> DoclingDocument. This is the slow, RAM-hungry step (~6 GB)."""
    return converter.convert(str(path)).document


def build_chunker(hf_tokenizer, max_tokens: int) -> HybridChunker:
    """Token-aware chunker bound to the *embedder's own* tokenizer, so a chunk
    can never be longer than what multilingual-e5-small will actually read
    (silently truncated chunks are invisible retrieval damage).

    docling-core moved tokenizers behind a wrapper class in later versions and
    deprecated passing a raw Hugging Face tokenizer. Both paths are kept until
    the installed version is known -- probe.py prints which one was used.
    """
    try:
        from docling_core.transforms.chunker.tokenizer.huggingface import (
            HuggingFaceTokenizer,
        )

        return HybridChunker(
            tokenizer=HuggingFaceTokenizer(tokenizer=hf_tokenizer, max_tokens=max_tokens)
        )
    except ImportError:
        return HybridChunker(tokenizer=hf_tokenizer, max_tokens=max_tokens)


def _page_no(chunk) -> int | None:
    """Lowest page number across the chunk's source items.

    Attribute names are read defensively: the exact shape of Docling's chunk
    metadata is confirmed by probe.py against the installed version, not
    assumed here.
    """
    pages: list[int] = []
    meta = getattr(chunk, "meta", None)
    for item in getattr(meta, "doc_items", None) or []:
        for prov in getattr(item, "prov", None) or []:
            page = getattr(prov, "page_no", None)
            if isinstance(page, int):
                pages.append(page)
    return min(pages) if pages else None


def _section_path(chunk) -> str | None:
    """Heading trail, e.g. 'Materials and Methods > Treatments'."""
    meta = getattr(chunk, "meta", None)
    headings = getattr(meta, "headings", None) or []
    cleaned = [" ".join(str(h).split()) for h in headings if h]
    return " > ".join(cleaned) if cleaned else None


def _contextualize(chunker: HybridChunker, chunk, fallback_text: str) -> str:
    """Chunk text with its headings prepended, for embedding.

    Docling exposes this as chunker.contextualize(chunk). Called positionally
    so a renamed keyword argument cannot break it; if the method is missing
    entirely we rebuild an equivalent string from the heading trail rather than
    silently embedding context-free text.
    """
    contextualize = getattr(chunker, "contextualize", None)
    if callable(contextualize):
        result = contextualize(chunk)
        if result:
            return str(result)

    section = _section_path(chunk)
    return f"{section}\n{fallback_text}" if section else fallback_text


def chunk_document(doc, chunker: HybridChunker) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    for chunk in chunker.chunk(dl_doc=doc):
        text = (getattr(chunk, "text", "") or "").strip()
        if not text:
            continue
        chunks.append(
            ParsedChunk(
                text=text,
                embed_text=_contextualize(chunker, chunk, text),
                page_no=_page_no(chunk),
                section_path=_section_path(chunk),
            )
        )
    return chunks
