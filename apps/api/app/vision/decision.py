"""The deterministic part that is allowed to say "no" (CLAUDE.md rule 5; docs/ai/multimodal-vision.md
step 5). Pure functions over plain values: no I/O, no model, no randomness, so every branch is a unit
test and a mutation check.

Two stages, because the second costs a vision-model call and a photo that is going to be refused anyway
should not be sent to a provider at all (cheaper, and the farmer's photo goes nowhere it need not):

  decide_quality                 the quality gate's verdict (a retake tip, nothing else runs).
  decide_before_second_opinion   out-of-distribution -> low confidence -> crop AgriAI does not know ->
                                 crop nobody measured. Returns a terminal Verdict, or None meaning
                                 "ask the second model".
  decide_with_second_opinion     the second model must independently name the same crop AND the same
                                 condition as the classifier's top choice. Anything else is a refusal.

Agreement is strict on purpose: the VLM naming the classifier's SECOND choice is a disagreement, not a
partial win. A diagnosis is shown only when two independent models name the same thing; top-3 is then
shown for transparency, with the agreed one first.

Reasons (abstained_because) are stable strings: the API, the UI messages and the eval report use them.
"""
from dataclasses import dataclass
from typing import Literal

from app.vision.calibration import Band, Calibration
from app.vision.classifier import Prediction
from app.vision.labels import Label, LabelMap
from app.vision.quality import QualityReport
from app.vision.vlm import NOT_A_PLANT, OTHER_CROP, OTHER_DISEASE, UNCLEAR, VlmObservation

Outcome = Literal["diagnosis", "abstained", "rejected_quality"]

# abstained_because values owned by this module.
OUT_OF_DISTRIBUTION = "out_of_distribution"
LOW_CONFIDENCE = "low_confidence"
CROP_NOT_SUPPORTED = "crop_not_supported"  # the model knows it (apple, grape...) but AgriAI has no such crop
CROP_NOT_VALIDATED = "crop_not_validated"  # AgriAI knows the crop but no field measurement qualified it
NOT_A_PLANT_PHOTO = "not_a_plant_photo"
MODEL_DISAGREEMENT = "model_disagreement"
VISION_UNAVAILABLE = "vision_unavailable"
VISION_NOT_CALIBRATED = "vision_not_calibrated"
QUALITY_REJECTED = "quality_rejected"
CROP_DIFFERS_FROM_FARM = "crop_differs_from_farm"


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    reason: str | None  # None only for a diagnosis
    detail: str | None = None  # a stable sub-reason, e.g. "wheat" for a model_disagreement about a crop the classifier lacks
    leading: Label | None = None  # set for a diagnosis (and for refusals that got far enough to have one)
    band: Band | None = None


def decide_quality(quality: QualityReport) -> Verdict | None:
    """A photo that fails the quality gate is rejected before anything else runs. None = it passed."""
    if quality.passed:
        return None
    return Verdict("rejected_quality", QUALITY_REJECTED, detail=",".join(quality.reasons))


def decide_before_second_opinion(prediction: Prediction, label_map: LabelMap, calibration: Calibration) -> Verdict | None:
    top = prediction.top[0]
    leading = label_map.by_index(top.index)

    if not prediction.in_distribution:
        # The classifier's own pick is not shown or used: for a photo it was never built for, it is noise.
        return Verdict("abstained", OUT_OF_DISTRIBUTION)
    if top.probability < calibration.min_probability:
        return Verdict("abstained", LOW_CONFIDENCE, leading=leading)
    if not leading.crop_known_to_agriai:
        return Verdict("abstained", CROP_NOT_SUPPORTED, detail=leading.crop, leading=leading)
    if not calibration.crop_enabled(leading.crop):
        return Verdict("abstained", CROP_NOT_VALIDATED, detail=leading.crop, leading=leading)
    return None


def decide_with_second_opinion(
    prediction: Prediction, observation: VlmObservation | None, label_map: LabelMap, calibration: Calibration
) -> Verdict:
    """`observation` None = the vision model could not be consulted (quota, network, unusable output)."""
    top = prediction.top[0]
    leading = label_map.by_index(top.index)
    if observation is None:
        return Verdict("abstained", VISION_UNAVAILABLE, leading=leading)

    if not observation.is_plant_photo or observation.crop == NOT_A_PLANT:
        return Verdict("abstained", NOT_A_PLANT_PHOTO, leading=leading)
    if observation.crop in (UNCLEAR, OTHER_CROP):
        return Verdict("abstained", MODEL_DISAGREEMENT, detail="crop_unclear", leading=leading)
    if observation.crop != leading.crop:
        # Includes wheat and rice, which the classifier has no class for: a photo the second model calls
        # wheat but the classifier calls tomato is exactly the case that must not become a diagnosis.
        return Verdict("abstained", MODEL_DISAGREEMENT, detail="crop_differs", leading=leading)
    if observation.condition in (UNCLEAR, OTHER_DISEASE):
        return Verdict("abstained", MODEL_DISAGREEMENT, detail="condition_unclear", leading=leading)
    if observation.condition != leading.condition:
        return Verdict("abstained", MODEL_DISAGREEMENT, detail="condition_differs", leading=leading)

    return Verdict("diagnosis", None, leading=leading, band=calibration.band_for(top.probability))


def decide_against_farm(leading: Label, farm_crop_keys: frozenset[str]) -> Verdict | None:
    """The farm record is evidence too. If it names a crop and the two models agree on a DIFFERENT one, nothing is
    diagnosed: the live measurement (evals/results/vision-pipeline-2026-10-10.md) found rice leaves, a crop the
    classifier has no class for, being called maize by the classifier and, once, by the second model too. A note
    beside a maize diagnosis is not enough for a farmer who recorded rice. No recorded crop, no check."""
    if farm_crop_keys and leading.crop not in farm_crop_keys:
        return Verdict("abstained", CROP_DIFFERS_FROM_FARM, detail=f"{leading.crop} vs {','.join(sorted(farm_crop_keys))}", leading=leading)
    return None
