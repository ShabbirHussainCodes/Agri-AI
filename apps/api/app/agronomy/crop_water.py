"""Crop and soil reference inputs for the water balance (ADR-0015).

These numbers (crop coefficients, stage lengths, rooting depth, depletion
fraction, soil water capacity) are the safety-relevant part of an irrigation
answer: the arithmetic is easy, a wrong input is not. ADR-0012 therefore
applies. Licence and provenance qualify a source, they do not qualify its
content, so the table is FAIL-CLOSED:

  * a row is used only when `status == "verified"`, with `verified_by`,
    `verified_on` and a `sources` entry for every value group;
  * a verified row with a missing or out-of-range value does not load at all;
  * anything else (unknown crop, unverified row, unknown soil) comes back as
    a reason code, never as a guessed default.

`find_crop` / `find_soil` return `(params, None)` or `(None, reason)`. The
engine (water_balance.py) only ever receives the typed, non-null params.

Pure functions, no network; tests/test_crop_water.py.
"""
import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SoilTexture = Literal["sandy", "loamy", "clayey"]

# apps/api/app/agronomy/crop_water.py -> repo root is four levels up. Not
# imported from app.core.config on purpose: that builds Settings() and needs
# environment variables, and this module must stay importable on its own.
DEFAULT_TABLE_PATH = Path(__file__).resolve().parents[4] / "data" / "crop_water" / "crop-water-v1.json"

# Reason codes (stable strings: they appear in the API response).
CROP_NOT_SUPPORTED = "crop_not_supported"
CROP_UNVERIFIED = "crop_reference_unverified"
SOIL_MISSING = "soil_texture_missing"
SOIL_UNVERIFIED = "soil_reference_unverified"


class CropTableError(ValueError):
    """The table file is malformed. Raised, never swallowed into a default."""


class StageDays(BaseModel):
    """The four FAO-56 growth stages, in days from sowing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    initial: int = Field(ge=1)
    development: int = Field(ge=1)
    mid: int = Field(ge=1)
    late: int = Field(ge=1)

    @property
    def total(self) -> int:
        return self.initial + self.development + self.mid + self.late


class CropParams(BaseModel):
    """What the engine receives: every field present and range-checked."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kc_ini: float = Field(gt=0, le=2.0)
    kc_mid: float = Field(gt=0, le=2.0)
    kc_end: float = Field(gt=0, le=2.0)
    stage_days: StageDays
    root_depth_m: float = Field(gt=0, le=3.0)
    p: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def _kc_shape(self) -> "CropParams":
        # ADR-0012 sanity check, applied to every row that can reach the
        # engine: a crop's coefficient peaks mid-season.
        if self.kc_mid < self.kc_ini or self.kc_mid < self.kc_end:
            raise ValueError("kc_mid must be at least kc_ini and kc_end (peak at mid-season)")
        return self


class SoilParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    texture: SoilTexture
    theta_fc: float = Field(gt=0, lt=0.7)  # m3/m3, field capacity
    theta_wp: float = Field(gt=0, lt=0.7)  # m3/m3, wilting point

    @model_validator(mode="after")
    def _fc_above_wp(self) -> "SoilParams":
        if self.theta_fc <= self.theta_wp:
            raise ValueError("theta_fc must be greater than theta_wp")
        return self


class _Row(BaseModel):
    """Provenance shared by crop and soil rows."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["unverified", "verified"]
    verified_by: str | None = None
    verified_on: date | None = None
    sources: dict[str, str] = {}
    notes: str = ""

    def _check_verified(self, value_fields: dict[str, object], source_keys: tuple[str, ...]) -> None:
        if self.status != "verified":
            return
        missing = [k for k, v in value_fields.items() if v is None or v == ""]
        if missing:
            raise ValueError(f"verified row has missing values: {missing}")
        if not (self.verified_by or "").strip() or self.verified_on is None:
            raise ValueError("verified row needs verified_by and verified_on")
        absent = [k for k in source_keys if not self.sources.get(k, "").strip()]
        if absent:
            raise ValueError(f"verified row needs a sources entry for: {absent}")


class CropRow(_Row):
    name_en: str
    kc_ini: float | None = None
    kc_mid: float | None = None
    kc_end: float | None = None
    stage_days: StageDays | None = None
    stage_length_basis: str | None = None
    root_depth_m: float | None = None
    p: float | None = None

    @model_validator(mode="after")
    def _validate(self) -> "CropRow":
        self._check_verified(
            {
                "kc_ini": self.kc_ini,
                "kc_mid": self.kc_mid,
                "kc_end": self.kc_end,
                "stage_days": self.stage_days,
                "stage_length_basis": self.stage_length_basis,
                "root_depth_m": self.root_depth_m,
                "p": self.p,
            },
            ("kc", "stage_days", "root_depth_m", "p"),
        )
        if self.status == "verified":
            # Re-uses the engine-side range and sanity checks, so a row that
            # loads as verified is exactly a row the engine would accept.
            self.to_params()
        return self

    def to_params(self) -> CropParams:
        if self.status != "verified":
            raise CropTableError(f"crop row {self.name_en!r} is not verified")
        return CropParams(
            name=self.name_en,
            kc_ini=self.kc_ini,  # type: ignore[arg-type]
            kc_mid=self.kc_mid,  # type: ignore[arg-type]
            kc_end=self.kc_end,  # type: ignore[arg-type]
            stage_days=self.stage_days,  # type: ignore[arg-type]
            root_depth_m=self.root_depth_m,  # type: ignore[arg-type]
            p=self.p,  # type: ignore[arg-type]
        )


class SoilRow(_Row):
    texture: SoilTexture
    fao56_class: str | None = None
    theta_fc: float | None = None
    theta_wp: float | None = None

    @model_validator(mode="after")
    def _validate(self) -> "SoilRow":
        self._check_verified(
            {"fao56_class": self.fao56_class, "theta_fc": self.theta_fc, "theta_wp": self.theta_wp},
            ("theta",),
        )
        if self.status == "verified":
            self.to_params()
        return self

    def to_params(self) -> SoilParams:
        if self.status != "verified":
            raise CropTableError(f"soil row {self.texture!r} is not verified")
        return SoilParams(
            texture=self.texture,
            theta_fc=self.theta_fc,  # type: ignore[arg-type]
            theta_wp=self.theta_wp,  # type: ignore[arg-type]
        )


class CropWaterTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_version: str
    method: str
    primary_source: str
    crops: list[CropRow]
    soils: list[SoilRow]

    @model_validator(mode="after")
    def _unique(self) -> "CropWaterTable":
        names = [c.name_en.strip().lower() for c in self.crops]
        if len(names) != len(set(names)):
            raise ValueError("duplicate crop name in table")
        textures = [s.texture for s in self.soils]
        if len(textures) != len(set(textures)):
            raise ValueError("duplicate soil texture in table")
        return self


def load_table(path: Path | None = None) -> CropWaterTable:
    """Reads and validates the table file. A malformed file raises
    CropTableError: it is a deployment error, not something to paper over."""
    target = path or DEFAULT_TABLE_PATH
    try:
        return CropWaterTable.model_validate(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:  # json errors and pydantic errors are ValueErrors
        raise CropTableError(f"crop water table {target} is unusable: {exc}") from exc


@lru_cache(maxsize=4)
def _cached_table(path: Path | None) -> CropWaterTable:
    return load_table(path)


def get_table(path: Path | None = None) -> CropWaterTable:
    """Cached per path: the file is read once per process."""
    return _cached_table(path)


def find_crop(table: CropWaterTable, crop_name: str | None) -> tuple[CropParams | None, str | None]:
    """Case-insensitive match on the crops table's English name."""
    key = (crop_name or "").strip().lower()
    for row in table.crops:
        if row.name_en.strip().lower() == key and key:
            if row.status != "verified":
                return None, CROP_UNVERIFIED
            return row.to_params(), None
    return None, CROP_NOT_SUPPORTED


def find_soil(table: CropWaterTable, texture: str | None) -> tuple[SoilParams | None, str | None]:
    if not texture:
        return None, SOIL_MISSING
    for row in table.soils:
        if row.texture == texture:
            if row.status != "verified":
                return None, SOIL_UNVERIFIED
            return row.to_params(), None
    return None, SOIL_MISSING
