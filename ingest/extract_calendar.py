"""RESEARCH / DIAGNOSTIC TOOL -- NOT PART OF THE INGESTION PATH.

Extracts the Mandla crop calendar (Appendix 1 of 10568/180614) as a real
table, for inspection by a human. Nothing here writes to the database, and
no production code imports this module.

OUTCOME OF THIS TOOL'S FIRST RUN (2026-09-08), which is why the warning above
matters: the extraction WORKED -- 64 crop rows, months assigned by column
position, verified cell by cell against page 12 of the PDF by a human. The
data it produced was nonetheless excluded from the corpus, because the source
table's own values are agronomically unsafe (it marks wheat suitable
June-October, inverting the rabi season). See
docs/decisions/ADR-0012-corpus-domain-sanity-validation.md and the reason
recorded beside `exclude_pages` in sources.yaml.

The calendar is NOT corrected here from general agronomic knowledge. Replacing
a source's values with our own assumptions, while still citing the source,
would be a worse failure than omitting the table.

HOW IT WORKS
The calendar is an image in the PDF, so OCR is the only thing that reads it,
and OCR gets the header row wrong (July came back as "Inf"). So the header
text is never trusted: column 0 is the crop and columns 1..12 are
January..December in order, months are assigned BY POSITION, and the OCR'd
header is used only as a sanity check that gets REPORTED (CLAUDE.md rule 7).
Anything that does not fit -- an unexpected column count, a cell that is not
0 or 1 -- is printed as a problem rather than quietly corrected.

    cd ingest && python extract_calendar.py
"""
import csv
import sys
from pathlib import Path

from config import INGEST_DIR, settings
from parse_chunk import build_converter, parse_pdf
from sources import load_approved_items

CALENDAR_HANDLE = "10568/180614"

MONTHS = [
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
]

# Written into the gitignored _cache/ directory, under a name that states
# what it is. Nothing in the ingestion path reads this file.
OUT_CSV = INGEST_DIR / "_cache" / "crop-calendar-RESEARCH-ONLY.csv"


def cell_text(grid, row: int, col: int) -> str:
    try:
        return " ".join(grid[row][col].text.split())
    except IndexError:
        return ""


def looks_like_calendar(table) -> bool:
    """A calendar table is one crop column plus twelve month columns.

    Deliberately shape-based: the header text is exactly what we do not trust.
    A tolerance of +/-1 column allows for a stray split column without letting
    an unrelated 5-column table through.
    """
    cols = table.data.num_cols
    return 12 <= cols <= 14 and table.data.num_rows >= 3


def main() -> int:
    item = next(
        (i for i in load_approved_items() if i.handle == CALENDAR_HANDLE), None
    )
    if item is None:
        print(f"{CALENDAR_HANDLE} is not an approved item in sources.yaml")
        return 1

    print("=" * 72)
    print("RESEARCH TOOL. Output is for human inspection only.")
    print("This calendar is EXCLUDED from the corpus -- see ADR-0012.")
    print("=" * 72)
    print(f"\nParsing {item.local_path.name} (OCR must stay ON -- the calendar is an image)")
    converter = build_converter(settings.docling_ocr, settings.docling_backend)
    doc = parse_pdf(converter, item.local_path)

    print(f"\nTables found in document: {len(doc.tables)}")
    for idx, table in enumerate(doc.tables):
        pages = sorted({p.page_no for p in (table.prov or [])})
        print(
            f"  [{idx}] {table.data.num_rows} rows x {table.data.num_cols} cols "
            f"| pages {pages} | calendar-shaped: {looks_like_calendar(table)}"
        )

    calendars = [t for t in doc.tables if looks_like_calendar(t)]
    if not calendars:
        print("\nNo calendar-shaped table found. Nothing written.")
        return 1

    rows: list[dict] = []
    problems: list[str] = []

    for t_idx, table in enumerate(calendars):
        grid = table.data.grid
        n_cols = table.data.num_cols
        pages = sorted({p.page_no for p in (table.prov or [])})

        # Sanity-check the header row against the positions we are about to
        # trust. Mismatches are reported, never silently accepted or "fixed".
        header = [cell_text(grid, 0, c) for c in range(n_cols)]
        for offset, expected in enumerate(MONTHS, start=1):
            if offset >= n_cols:
                problems.append(
                    f"table {t_idx} (pages {pages}): only {n_cols} columns, "
                    f"expected 13 -- {expected.title()} has no column"
                )
                continue
            got = header[offset].lower()
            if not got.startswith(expected[:3]):
                problems.append(
                    f"table {t_idx} (pages {pages}): column {offset} header reads "
                    f"{header[offset]!r}, position says {expected.title()} "
                    "-- using the position"
                )

        for r in range(1, table.data.num_rows):
            crop = cell_text(grid, r, 0)
            if not crop:
                continue

            row = {"crop": crop, "source_pages": ",".join(map(str, pages))}
            for offset, month in enumerate(MONTHS, start=1):
                value = cell_text(grid, r, offset) if offset < n_cols else ""
                if value not in ("0", "1", ""):
                    problems.append(
                        f"table {t_idx}: crop {crop!r}, {month.title()} = {value!r} "
                        "-- expected 0 or 1"
                    )
                row[month] = value
            rows.append(row)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["crop", *MONTHS, "source_pages"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nExtracted {len(rows)} crop rows -> {OUT_CSV}")

    if problems:
        print(f"\n{len(problems)} problem(s) to check against the PDF:")
        for p in problems[:40]:
            print(f"  ! {p}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
    else:
        print("\nNo header or value problems detected.")

    print(
        "\nNOTHING has been written to the database, and nothing in the "
        "ingestion path reads this file. Pages 11-13 of this document are "
        "excluded from the corpus (sources.yaml, ADR-0012)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
