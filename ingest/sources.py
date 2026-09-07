"""Reads ingest/sources.yaml -- the licence register -- and hands the
pipeline only the items a human has actually approved.

The register is the answer to "where did your corpus come from and are you
allowed to use it?", so the pipeline reads it rather than taking a file path
on the command line: a PDF that is not registered and approved cannot be
ingested by accident.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml

from config import INGEST_DIR

SOURCES_FILE = INGEST_DIR / "sources.yaml"

# Licences that are safe for a project that may be commercialised later
# (approved 2026-09-07). Anything NonCommercial, ShareAlike, or unstated is
# refused here rather than being caught later by a human reading a diff.
ALLOWED_LICENCES = {"CC-BY-4.0", "CC-BY-3.0-IGO", "apache-2.0", "GODL-India"}


@dataclass(frozen=True)
class ApprovedItem:
    """One document a human approved for ingestion."""

    source_id: str
    handle: str
    title: str
    item_url: str
    publisher: str | None
    year: int | None
    doc_type: str
    licence: str
    language: str
    local_path: Path
    crop_name: str | None
    state: str | None

    # Pages of this PDF that must never reach the corpus. Set per item in
    # sources.yaml WITH a written reason, so an exclusion is a reviewable
    # decision in Git rather than an invisible filter in code.
    exclude_pages: frozenset[int]


def _clean(text: str | None) -> str | None:
    """YAML block scalars keep their newlines; titles and notes read better
    as single lines once they reach the database."""
    if text is None:
        return None
    return " ".join(text.split())


def load_approved_items() -> list[ApprovedItem]:
    register = yaml.safe_load(SOURCES_FILE.read_text())
    items: list[ApprovedItem] = []

    for source in register.get("sources") or []:
        for raw in source.get("approved_items") or []:
            licence = raw["licence"]
            if licence not in ALLOWED_LICENCES:
                raise ValueError(
                    f"{raw['handle']}: licence {licence!r} is not in the "
                    f"commercial-safe allow-list {sorted(ALLOWED_LICENCES)}. "
                    "Refusing to ingest."
                )

            local_path = INGEST_DIR / raw["local_file"]
            if not local_path.exists():
                raise FileNotFoundError(
                    f"{raw['handle']}: {local_path} is missing. Download it "
                    "first (see ingest/README.md); _downloads/ is gitignored."
                )

            languages = raw.get("languages") or ["en"]
            items.append(
                ApprovedItem(
                    source_id=source["id"],
                    handle=raw["handle"],
                    title=_clean(raw["title"]),
                    item_url=raw["item_url"],
                    publisher=_clean(raw.get("publisher")),
                    year=raw.get("year"),
                    doc_type=raw["doc_type"],
                    licence=licence,
                    language=languages[0],
                    local_path=local_path,
                    crop_name=raw.get("crop_name"),
                    state=raw.get("state"),
                    exclude_pages=frozenset(raw.get("exclude_pages") or []),
                )
            )

    return items
