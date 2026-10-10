"""Verified label rows and the label card (CLAUDE.md rule 1, ADR-0005, ADR-0016).

The only way a dose or a waiting period reaches a farmer. A row of
data/agrochemical/major-uses-v1.json is copied by CODE into a `LabelEntry`; the
model never writes those numbers and never even sees them (app/agent/tools/
agrochemical.py tells it only that a card will be shown).

The table is FAIL-CLOSED, like the crop table (ADR-0012, ADR-0015):

  * a row is used only when `status == "verified"`, with `verified_by`,
    `verified_on` and a `source_ref` (document, date, page);
  * a verified row needs every value a farmer would act on: the formulation, a
    formulation dose with its unit, a waiting period, a label date; a missing or
    out-of-range value means the file does not load at all;
  * a row whose molecule is on the denylist is never returned, even if someone
    entered it as verified.

No row ships: every lookup answers `no_verified_entry` until a human reads the
CIB&RC document and adds rows (data/agrochemical/README.md).

The card says what it is: a summary of CIB&RC "Major Uses", with the product
pack label as the legal source. Pure functions, no network.
"""
import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.safety import chemical_guard
from app.safety.crop_scope import KNOWN_CROPS, _tokens

DEFAULT_TABLE_PATH = Path(__file__).resolve().parents[4] / "data" / "agrochemical" / "major-uses-v1.json"

NO_VERIFIED_ENTRY = "no_verified_entry"

DoseUnit = Literal["g", "ml"]


class AgrochemTableError(ValueError):
    """The table file is malformed. Raised, never swallowed into "no rows"."""


class AgrochemRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    molecule: str
    molecule_aliases: list[str] = []
    formulation: str | None = None  # e.g. "Mancozeb 75% WP", as printed
    crop: str  # a canonical crop key (app/safety/crop_scope.CROP_LEXICON)
    pest: str
    pest_aliases: list[str] = []
    dose_ai_g_per_ha: float | None = Field(default=None, gt=0, le=100000)
    dose_formulation: float | None = Field(default=None, gt=0, le=100000)
    dose_formulation_unit: DoseUnit | None = None
    dilution_l_per_ha: float | None = Field(default=None, gt=0, le=100000)
    waiting_period_days: int | None = Field(default=None, ge=0, le=365)
    label_date: date | None = None
    source_ref: str | None = None
    status: Literal["unverified", "verified"]
    verified_by: str | None = None
    verified_on: date | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _check(self) -> "AgrochemRow":
        if not self.id.strip() or self.molecule != self.molecule.strip().lower() or not self.molecule:
            raise ValueError("id and a lower-case molecule are required")
        if self.crop not in KNOWN_CROPS:
            raise ValueError(f"crop {self.crop!r} is not a canonical crop key")
        if self.status == "verified":
            missing = [
                name for name, value in {
                    "formulation": self.formulation, "dose_formulation": self.dose_formulation,
                    "dose_formulation_unit": self.dose_formulation_unit,
                    "waiting_period_days": self.waiting_period_days, "label_date": self.label_date,
                    "source_ref": self.source_ref, "verified_by": self.verified_by, "verified_on": self.verified_on,
                }.items() if value is None or value == "" or (isinstance(value, str) and not value.strip())
            ]
            if missing or not self.pest.strip():
                raise ValueError(f"verified row has missing values: {missing or ['pest']}")
        return self


class AgrochemTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_version: str
    primary_source: str
    rows: list[AgrochemRow]

    @model_validator(mode="after")
    def _unique_ids(self) -> "AgrochemTable":
        ids = [r.id for r in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate row id")
        return self


def load_table(path: Path | None = None) -> AgrochemTable:
    target = path or DEFAULT_TABLE_PATH
    try:
        return AgrochemTable.model_validate(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise AgrochemTableError(f"agrochemical table {target} is unusable: {exc}") from exc


@lru_cache(maxsize=4)
def _cached(path: Path | None) -> AgrochemTable:
    return load_table(path)


def get_table(path: Path | None = None) -> AgrochemTable:
    """Cached per path: the file is read once per process (restart after editing)."""
    return _cached(path)


def _norm(text: str) -> str:
    return " ".join(_tokens(text))


def lookup(
    table: AgrochemTable,
    denylist: chemical_guard.Denylist,
    *,
    crop: str,
    pest: str,
    molecule: str | None = None,
) -> tuple[list[AgrochemRow], str | None]:
    """Verified rows for this canonical crop and pest (and molecule, if given):
    `(rows, None)`, or `([], NO_VERIFIED_ENTRY)`. Never returns an unverified row
    or a row whose molecule is on the denylist."""
    want_pest = _norm(pest)
    want_molecule = _norm(molecule) if molecule else None
    rows = []
    for row in table.rows:
        if row.status != "verified" or row.crop != crop:
            continue
        if want_pest not in {_norm(p) for p in [row.pest, *row.pest_aliases]}:
            continue
        if want_molecule is not None and want_molecule not in {_norm(m) for m in [row.molecule, *row.molecule_aliases]}:
            continue
        if chemical_guard.find_banned([row.molecule, *row.molecule_aliases], denylist):
            continue
        rows.append(row)
    return (rows, None) if rows else ([], NO_VERIFIED_ENTRY)


class LabelEntry(BaseModel):
    """One label card in the farmer's response. Every field is copied by code
    from a verified table row; the model never authors any of it."""

    model_config = ConfigDict(extra="forbid")

    row_id: str
    molecule: str
    formulation: str
    crop: str
    pest: str
    dose_formulation: float
    dose_formulation_unit: DoseUnit
    dose_ai_g_per_ha: float | None = None
    dilution_l_per_ha: float | None = None
    waiting_period_days: int
    label_date: date
    source_ref: str
    table_version: str
    text: str  # the same facts as a bilingual card, for a client that shows only text


def _g(value: float) -> str:
    return f"{value:g}"


def entry_from_row(row: AgrochemRow, table_version: str) -> LabelEntry:
    """Rows reaching here are verified, so the optionals the card needs are set."""
    assert row.formulation and row.dose_formulation is not None and row.dose_formulation_unit
    assert row.waiting_period_days is not None and row.label_date and row.source_ref
    unit = row.dose_formulation_unit
    extra_en = ""
    extra_hi = ""
    if row.dose_ai_g_per_ha is not None:
        extra_en += f" (active ingredient {_g(row.dose_ai_g_per_ha)} g per hectare)"
        extra_hi += f" (सक्रिय तत्व {_g(row.dose_ai_g_per_ha)} ग्राम प्रति हेक्टेयर)"
    if row.dilution_l_per_ha is not None:
        extra_en += f", in {_g(row.dilution_l_per_ha)} litres of water per hectare"
        extra_hi += f", {_g(row.dilution_l_per_ha)} लीटर पानी प्रति हेक्टेयर में"
    unit_hi = "ग्राम" if unit == "g" else "मिली"
    text = (
        f"{row.formulation} on {row.crop} for {row.pest}: {_g(row.dose_formulation)} {unit} per hectare{extra_en}. "
        f"Waiting period: {row.waiting_period_days} days. Source: {row.source_ref} (label date {row.label_date}, "
        f"table {table_version}). This summarises CIB&RC \"Major Uses\"; always follow the label on the product pack.\n"
        f"{row.formulation}, {row.crop}, {row.pest}: {_g(row.dose_formulation)} {unit_hi} प्रति हेक्टेयर{extra_hi}। "
        f"छिड़काव के बाद फसल तोड़ने से पहले {row.waiting_period_days} दिन रुकें। स्रोत: {row.source_ref} (लेबल की तारीख {row.label_date}, "
        f"तालिका {table_version})। यह CIB&RC \"Major Uses\" का सार है; हमेशा दवा के पैकेट पर छपे लेबल का पालन करें।"
    )
    return LabelEntry(
        row_id=row.id, molecule=row.molecule, formulation=row.formulation, crop=row.crop, pest=row.pest,
        dose_formulation=row.dose_formulation, dose_formulation_unit=unit,
        dose_ai_g_per_ha=row.dose_ai_g_per_ha, dilution_l_per_ha=row.dilution_l_per_ha,
        waiting_period_days=row.waiting_period_days, label_date=row.label_date, source_ref=row.source_ref,
        table_version=table_version, text=text,
    )
