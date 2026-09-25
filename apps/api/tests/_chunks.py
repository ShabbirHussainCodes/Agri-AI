"""Builders for RetrievedChunk objects in pure unit tests (no database)."""
import uuid

from app.retrieval.hybrid import RetrievedChunk


def make_chunk(content: str, *, page: int = 3, title: str = "Tomato IPDM trial") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        handle="10568/180732",
        doc_title=title,
        publisher="CGIAR",
        published_year=2024,
        doc_type="journal_article",
        licence="CC-BY-4.0",
        url="https://example.org/10568/180732",
        page_no=page,
        section_path="Materials and methods",
        language="en",
        content=content,
        dense_similarity=0.84,
        dense_rank=1,
        lexical_rank=1,
        rrf_score=0.039,
    )
