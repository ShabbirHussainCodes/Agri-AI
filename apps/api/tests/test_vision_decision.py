"""Every branch of the deterministic decision (app/vision/decision.py). Pure values, no models."""
import pytest

from app.vision import decision as D
from app.vision import quality
from app.vision.classifier import Prediction, Ranked
from app.vision.vlm import VlmObservation

from ._vision_fixtures import (
    APPLE_SCAB,
    LABELS,
    ORANGE_HLB,
    POTATO_EARLY,
    TOMATO_EARLY,
    TOMATO_HEALTHY,
    TOMATO_LATE,
    make_calibration,
)

CAL = make_calibration(min_probability=0.5, enabled_crops=("tomato",))


def prediction(top: int, p: float = 0.95, *, in_dist: bool = True, others=(TOMATO_LATE, TOMATO_HEALTHY)) -> Prediction:
    rest = (1 - p) / 2
    return Prediction(
        top=(Ranked(top, p, 9.0), Ranked(others[0], rest, 1.0), Ranked(others[1], rest, 0.5)),
        scores={"max_logit": 9.0},
        ood_score=9.0,
        in_distribution=in_dist,
    )


def seen(crop="tomato", condition="early_blight", *, plant=True, part="leaf", text="brown rings") -> VlmObservation:
    return VlmObservation(is_plant_photo=plant, plant_part=part, crop=crop, condition=condition, visible_symptoms=text)


def report(*reasons: str) -> quality.QualityReport:
    m = quality.QualityMetrics(640, 480, 200.0, 110.0, 0.0, 0.0, 0.4)
    return quality.QualityReport(passed=not reasons, reasons=tuple(reasons), metrics=m, thresholds_version="t")


# ----- quality ------------------------------------------------------------------------------------------

def test_a_passed_quality_report_does_not_stop_anything():
    assert D.decide_quality(report()) is None


def test_a_failed_quality_report_is_a_rejection_that_names_every_reason():
    v = D.decide_quality(report(quality.TOO_BLURRY, quality.TOO_DARK))
    assert (v.outcome, v.reason, v.detail) == ("rejected_quality", D.QUALITY_REJECTED, "too_blurry,too_dark")


# ----- before the second opinion ------------------------------------------------------------------------

def test_a_confident_in_distribution_enabled_crop_goes_on_to_the_second_model():
    assert D.decide_before_second_opinion(prediction(TOMATO_EARLY), LABELS, CAL) is None


def test_out_of_distribution_is_refused_and_the_classifiers_guess_is_dropped():
    v = D.decide_before_second_opinion(prediction(TOMATO_EARLY, in_dist=False), LABELS, CAL)
    assert (v.outcome, v.reason) == ("abstained", D.OUT_OF_DISTRIBUTION) and v.leading is None


def test_low_probability_is_refused_even_when_in_distribution():
    v = D.decide_before_second_opinion(prediction(TOMATO_EARLY, p=0.49), LABELS, CAL)
    assert v.reason == D.LOW_CONFIDENCE
    assert D.decide_before_second_opinion(prediction(TOMATO_EARLY, p=0.50), LABELS, CAL) is None  # the floor is inclusive


def test_a_crop_the_model_knows_but_agriai_does_not_is_not_supported():
    v = D.decide_before_second_opinion(prediction(APPLE_SCAB), LABELS, CAL)
    assert (v.reason, v.detail) == (D.CROP_NOT_SUPPORTED, "apple")


def test_a_known_crop_that_no_field_measurement_qualified_is_not_validated():
    v = D.decide_before_second_opinion(prediction(POTATO_EARLY), LABELS, CAL)
    assert (v.reason, v.detail) == (D.CROP_NOT_VALIDATED, "potato")


def test_a_label_without_a_healthy_counterpart_is_refused_when_its_crop_is_not_enabled():
    assert D.decide_before_second_opinion(prediction(ORANGE_HLB), LABELS, CAL).reason == D.CROP_NOT_VALIDATED


def test_the_order_of_the_checks_out_of_distribution_wins_over_everything():
    v = D.decide_before_second_opinion(prediction(APPLE_SCAB, p=0.1, in_dist=False), LABELS, CAL)
    assert v.reason == D.OUT_OF_DISTRIBUTION


# ----- the second opinion -------------------------------------------------------------------------------

def test_agreement_on_crop_and_condition_is_a_diagnosis_with_the_calibrated_band():
    v = D.decide_with_second_opinion(prediction(TOMATO_EARLY, p=0.95), seen(), LABELS, CAL)
    assert (v.outcome, v.reason) == ("diagnosis", None)
    assert v.leading.label == "Tomato___Early_blight" and v.band.name == "high"
    assert D.decide_with_second_opinion(prediction(TOMATO_EARLY, p=0.75), seen(), LABELS, CAL).band.name == "medium"
    assert D.decide_with_second_opinion(prediction(TOMATO_EARLY, p=0.55), seen(), LABELS, CAL).band.name == "low"


def test_no_second_opinion_available_is_an_honest_refusal():
    v = D.decide_with_second_opinion(prediction(TOMATO_EARLY), None, LABELS, CAL)
    assert v.reason == D.VISION_UNAVAILABLE


@pytest.mark.parametrize("obs", [seen(plant=False), seen(crop="not_a_plant")])
def test_the_second_model_saying_it_is_not_a_plant_is_a_refusal(obs):
    assert D.decide_with_second_opinion(prediction(TOMATO_EARLY), obs, LABELS, CAL).reason == D.NOT_A_PLANT_PHOTO


@pytest.mark.parametrize("crop", ["unclear", "other_crop"])
def test_a_crop_the_second_model_cannot_name_is_a_disagreement(crop):
    v = D.decide_with_second_opinion(prediction(TOMATO_EARLY), seen(crop=crop), LABELS, CAL)
    assert (v.reason, v.detail) == (D.MODEL_DISAGREEMENT, "crop_unclear")


@pytest.mark.parametrize("crop", ["wheat", "rice", "potato", "apple"])
def test_a_different_crop_is_a_disagreement_including_crops_the_classifier_lacks(crop):
    v = D.decide_with_second_opinion(prediction(TOMATO_EARLY), seen(crop=crop), LABELS, CAL)
    assert (v.reason, v.detail) == (D.MODEL_DISAGREEMENT, "crop_differs")


@pytest.mark.parametrize("condition", ["unclear", "other_disease"])
def test_a_condition_the_second_model_cannot_name_is_a_disagreement(condition):
    v = D.decide_with_second_opinion(prediction(TOMATO_EARLY), seen(condition=condition), LABELS, CAL)
    assert (v.reason, v.detail) == (D.MODEL_DISAGREEMENT, "condition_unclear")


def test_naming_the_classifiers_second_choice_is_a_disagreement_not_a_partial_win():
    v = D.decide_with_second_opinion(prediction(TOMATO_EARLY), seen(condition="late_blight"), LABELS, CAL)
    assert (v.reason, v.detail) == (D.MODEL_DISAGREEMENT, "condition_differs")


def test_healthy_against_a_disease_is_a_disagreement_both_ways():
    assert D.decide_with_second_opinion(prediction(TOMATO_EARLY), seen(condition="healthy"), LABELS, CAL).reason == D.MODEL_DISAGREEMENT
    assert D.decide_with_second_opinion(prediction(TOMATO_HEALTHY), seen(condition="early_blight"), LABELS, CAL).reason == D.MODEL_DISAGREEMENT
    assert D.decide_with_second_opinion(prediction(TOMATO_HEALTHY), seen(condition="healthy"), LABELS, CAL).outcome == "diagnosis"


def test_a_disagreement_still_names_what_the_classifier_thought_for_the_log_but_a_diagnosis_needs_both():
    v = D.decide_with_second_opinion(prediction(TOMATO_EARLY), seen(crop="wheat"), LABELS, CAL)
    assert v.outcome == "abstained" and v.band is None
