"""The classifier's label space (data/vision/label-map-v1.json): which index means which crop and
condition, with display names. Identity data only. Which crops may actually be diagnosed is a MEASURED
decision that lives in the calibration file (app/vision/calibration.py), not here.
"""
import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

from app.safety.crop_scope import KNOWN_CROPS

DEFAULT_PATH = Path(__file__).resolve().parents[4] / "data" / "vision" / "label-map-v1.json"

HEALTHY = "healthy"


class LabelMapError(ValueError):
    """The label map is malformed. Raised, never swallowed into an empty map."""


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    label: str  # the model's own class string
    crop: str  # a canonical crop key when AgriAI knows the crop, else a plain English key
    condition: str
    name_en: str
    name_hi: str
    name_hi_status: str  # "unreviewed" until a Hindi speaker has read it
    # The pest string used to look up a verified pesticide label row for this condition, or None.
    pest_for_label_lookup: str | None = None

    @property
    def is_healthy(self) -> bool:
        return self.condition == HEALTHY

    @property
    def crop_known_to_agriai(self) -> bool:
        """The crop is in AgriAI's own crop vocabulary (app/safety/crop_scope.py), so a farm can grow it
        and a label row can exist. Apple, grape and the like are in the model's label space but not in
        AgriAI's."""
        return self.crop in KNOWN_CROPS


class LabelMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    model: str
    note: str
    labels: list[Label]

    @model_validator(mode="after")
    def _check(self) -> "LabelMap":
        if [lab.index for lab in self.labels] != list(range(len(self.labels))):
            raise ValueError("label indexes must be 0..n-1 in order")
        names = [lab.label for lab in self.labels]
        if len(set(names)) != len(names):
            raise ValueError("duplicate label")
        return self

    def by_index(self, index: int) -> Label:
        return self.labels[index]

    def crops(self) -> list[str]:
        return sorted({lab.crop for lab in self.labels})


def load_label_map(path: Path | None = None) -> LabelMap:
    target = path or DEFAULT_PATH
    try:
        return LabelMap.model_validate(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise LabelMapError(f"label map {target} is unusable: {exc}") from exc


@lru_cache(maxsize=2)
def _cached(path: Path | None) -> LabelMap:
    return load_label_map(path)


def get_label_map(path: Path | None = None) -> LabelMap:
    return _cached(path)
