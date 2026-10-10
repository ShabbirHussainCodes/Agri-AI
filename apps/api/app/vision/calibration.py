"""What the classifier's numbers MEAN, measured on field photos (CLAUDE.md rule 4: accuracy is a measured
output, never a promise).

data/vision/calibration-v1.json is written by evals/vision/calibrate.py from a calibration split that is
disjoint from the test split the report quotes. It holds:

  * a temperature, fitted so that the classifier's probabilities are not over-confident on field photos;
  * the out-of-distribution score that separated supported leaves from everything else best on the
    calibration split, and its threshold;
  * confidence bands, each with the accuracy actually observed on the calibration split, so the farmer
    is shown "high / medium / low" and the UI can say on what that was measured;
  * per-crop enablement: a crop is diagnosed only if the calibration split showed it meets the rule that
    was written down before the measurement (evals/vision/README.md).

FAIL-CLOSED, like the crop-water and agrochemical tables: a missing file, an unparseable file, or
status != "calibrated" means NO diagnosis is ever given (every photo gets `vision_not_calibrated`).
A classifier nobody calibrated has numbers that mean nothing.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path(__file__).resolve().parents[4] / "data" / "vision" / "calibration-v1.json"

OodScore = Literal["msp", "max_logit", "energy", "feature_cosine"]
BandName = Literal["high", "medium", "low"]


class CalibrationError(ValueError):
    """The calibration file is malformed. Raised, never swallowed into "uncalibrated"."""


class Band(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: BandName
    min_probability: float = Field(ge=0, le=1)  # calibrated top-1 probability at or above this
    observed_accuracy: float = Field(ge=0, le=1)  # on the calibration split, for answers in this band
    n: int = Field(ge=0)


class CropDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    n_calibration: int = Field(ge=0)
    selective_accuracy: float | None = Field(default=None, ge=0, le=1)
    reason: str


class OodConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: OodScore
    # A photo is in-distribution when its score is at or above this. The scores are all "higher means
    # more like a supported leaf" (energy is stored negated).
    threshold: float
    # Per-class unit centroids of penultimate features, only for score == "feature_cosine".
    centroids: list[list[float]] | None = None


class Calibration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    status: Literal["calibrated", "uncalibrated"]
    model: dict[str, str]  # repo, revision, file, sha256 of the ONNX file this was calibrated for
    temperature: float = Field(gt=0, le=20)
    ood: OodConfig
    min_probability: float = Field(ge=0, le=1)  # top-1 calibrated probability below this = abstain
    bands: list[Band]
    crops: dict[str, CropDecision]
    calibrated_on: str
    generated_by: str
    date: str
    report: str  # path of the committed result this was derived from

    @model_validator(mode="after")
    def _check(self) -> "Calibration":
        if self.status == "calibrated":
            if not self.bands:
                raise ValueError("a calibrated file needs bands")
            floors = [b.min_probability for b in self.bands]
            if floors != sorted(floors, reverse=True) or [b.name for b in self.bands] != ["high", "medium", "low"][: len(self.bands)]:
                raise ValueError("bands must be ordered high, medium, low with falling floors")
            if self.ood.score == "feature_cosine" and not self.ood.centroids:
                raise ValueError("feature_cosine needs centroids")
        return self

    def band_for(self, probability: float) -> Band:
        for band in self.bands:
            if probability >= band.min_probability:
                return band
        return self.bands[-1]

    def crop_enabled(self, crop: str) -> bool:
        decision = self.crops.get(crop)
        return bool(decision and decision.enabled)


def load_calibration(path: Path | None = None) -> Calibration:
    target = path or DEFAULT_PATH
    try:
        return Calibration.model_validate(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise CalibrationError(f"calibration {target} is unusable: {exc}") from exc


@lru_cache(maxsize=2)
def _cached(path: Path | None) -> Calibration:
    return load_calibration(path)


def get_calibration(path: Path | None = None) -> Calibration:
    return _cached(path)
