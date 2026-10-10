"""DiagnosisResponse: what the farmer receives for a crop photo (docs/api/api-contracts.md, ADR-0018).

Built by code (app/vision/diagnose.py), like AdvisoryResponse (ADR-0013). It keeps the three things the
design requires apart on screen: what the models SAW (`model_saw`, `candidates`), what the LABEL says
(`advisory.agrochemical_label` and `advisory.retrieved_evidence`, copied by code from verified data and
validated quotes), and the final RECOMMENDATION (`advisory.recommendation`).

Three outcomes:
  rejected_quality   the photo cannot be read (blurry, dark ...): "take a better photo". Nothing else ran.
  abstained          the photo was readable, but code will not name a disease (out of distribution, the two
                     models disagree, a crop nobody measured ...). Abstention is an outcome, not an error.
  diagnosis          two independent models named the same crop and condition. `advisory` holds the
                     evidence-typed answer, produced and checked by the same stack as /ask.

No raw softmax is shown as "confidence": the only confidence shown is `band`, with the accuracy that
band actually had on field photos and what that was measured on.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.advisory import AdvisoryResponse

ScanOutcome = Literal["rejected_quality", "abstained", "diagnosis"]


class ScanCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    crop: str
    condition: str
    name_en: str
    name_hi: str
    name_hi_status: str
    # Calibrated probability from the classifier. For the API and the evals; the app never shows it as a
    # percentage (it is a model score, not an accuracy).
    probability: float = Field(ge=0, le=1)
    leading: bool
    # True only for the leading candidate, and only when the second model independently named the same
    # crop and condition.
    second_opinion_agrees: bool = False


class ConfidenceBand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["high", "medium", "low"]
    # What this band actually scored, on which photos. Words, not a promise (CLAUDE.md rule 4).
    observed_accuracy: float = Field(ge=0, le=1)
    n: int
    measured_on: str


class QualityInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    reasons: list[str]
    thresholds_version: str
    sharpness: float
    mean_luma: float
    vegetation_fraction: float
    width: int
    height: int


class ModelSaw(BaseModel):
    """What the second (vision-language) model reported about the photo, forced into a closed vocabulary.
    `symptoms` is its one free sentence, after the dose and banned-molecule guards."""

    model_config = ConfigDict(extra="forbid")

    plant_part: str
    crop: str
    condition: str
    symptoms: str


class ModelVersions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classifier: str
    calibration: str
    label_map: str
    vision_model: str | None = None


class DiagnosisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: ScanOutcome
    abstained_because: str | None = None
    # A sub-reason for an abstention (e.g. "crop_differs"), stable string, for the eval and the app.
    detail: str | None = None
    # Code-authored, bilingual (Hindi, blank line, English): the retake tip or the reason for not naming a
    # disease. Empty for a diagnosis, whose text is advisory.recommendation.
    message: str = ""
    quality: QualityInfo
    candidates: list[ScanCandidate] = []
    band: ConfidenceBand | None = None
    model_saw: ModelSaw | None = None
    advisory: AdvisoryResponse | None = None
    # Code-authored note attached to every diagnosis: automatic check, not an expert's confirmation.
    note: str = ""
    versions: ModelVersions
    # Filled by the router after the row is saved.
    scan_id: UUID | None = None
    image_path: str | None = None
    created_at: datetime | None = None
