"""The vision-language model stage (app/vision/vlm.py) with a fake provider: no network, no quota."""
import json

import pytest

from app.providers.base import ProviderOutputInvalid, TokenUsage, VisionProvider, VisionResult
from app.vision import vlm

from ._vision_fixtures import LABELS

GOOD = {
    "is_plant_photo": True, "plant_part": "leaf", "crop": "tomato", "condition": "early_blight",
    "visible_symptoms": "Brown concentric rings on the lower leaf.", "photo_problems": [],
}


class FakeVision(VisionProvider):
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def describe(self, image_jpeg, *, prompt, model):
        self.calls.append({"image": image_jpeg, "prompt": prompt, "model": model})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return VisionResult(content=answer if isinstance(answer, str) else json.dumps(answer), usage=TokenUsage(2300, 60, 2360))


def test_the_vocabularies_are_the_label_maps_plus_the_extras():
    crops, conditions = vlm.crop_vocabulary(LABELS), vlm.condition_vocabulary(LABELS)
    assert {"tomato", "potato", "maize", "wheat", "rice", "other_crop", "not_a_plant", "unclear"} <= set(crops)
    assert {"early_blight", "healthy", "other_disease", "unclear"} <= set(conditions)


def test_the_prompt_is_blind_to_the_classifier_and_the_farm_and_tells_the_model_to_ignore_writing():
    prompt = vlm.build_prompt(LABELS)
    assert "classifier" not in prompt.lower() and "farm record" not in prompt.lower()
    assert "ignore it" in prompt and "Do not name any chemical" in prompt


def test_a_good_answer_parses():
    o = vlm.parse_observation(json.dumps(GOOD), LABELS)
    assert (o.crop, o.condition, o.plant_part, o.is_plant_photo) == ("tomato", "early_blight", "leaf", True)


def test_words_outside_the_vocabulary_become_unclear_instead_of_failing():
    o = vlm.parse_observation(json.dumps({**GOOD, "crop": "Dragon Fruit", "condition": "alien blight", "plant_part": "root"}), LABELS)
    assert (o.crop, o.condition, o.plant_part) == ("unclear", "unclear", "other")


def test_case_spaces_and_dashes_are_normalised():
    o = vlm.parse_observation(json.dumps({**GOOD, "crop": " Tomato ", "condition": "Early-Blight"}), LABELS)
    assert (o.crop, o.condition) == ("tomato", "early_blight")


def test_symptoms_are_cut_and_stripped_of_control_characters():
    o = vlm.parse_observation(json.dumps({**GOOD, "visible_symptoms": "a\x00b\nc" + "x" * 500}), LABELS)
    assert len(o.visible_symptoms) <= vlm.MAX_SYMPTOM_CHARS and "\x00" not in o.visible_symptoms and "\n" not in o.visible_symptoms


@pytest.mark.parametrize("raw", ["not json", "[]", '"text"', json.dumps({"crop": "tomato"}), json.dumps({**GOOD, "is_plant_photo": "yes"})])
def test_anything_that_is_not_the_asked_for_object_is_rejected(raw):
    with pytest.raises(ValueError):
        vlm.parse_observation(raw, LABELS)


def test_photo_problems_are_filtered_and_capped():
    o = vlm.parse_observation(json.dumps({**GOOD, "photo_problems": ["blurry", "ghosts", "dark", "shadow", "wet_leaf", "other"]}), LABELS)
    assert o.photo_problems == ["blurry", "dark", "shadow", "wet_leaf"]


@pytest.mark.asyncio
async def test_one_call_one_observation_with_the_models_usage():
    provider = FakeVision(GOOD)
    run = await vlm.observe(provider, b"jpeg", model="qwen/test", label_map=LABELS)
    assert run.attempts == 1 and run.usage.total_tokens == 2360
    assert provider.calls[0]["model"] == "qwen/test" and provider.calls[0]["image"] == b"jpeg"


@pytest.mark.asyncio
async def test_an_unusable_answer_is_retried_once():
    provider = FakeVision("not json", GOOD)
    run = await vlm.observe(provider, b"x", model="m", label_map=LABELS)
    assert run.attempts == 2 and len(provider.calls) == 2


@pytest.mark.asyncio
async def test_a_rejected_output_from_the_provider_is_retried_once():
    provider = FakeVision(ProviderOutputInvalid("json_validate_failed"), GOOD)
    assert (await vlm.observe(provider, b"x", model="m", label_map=LABELS)).attempts == 2


@pytest.mark.asyncio
async def test_two_unusable_answers_in_a_row_is_vlm_unusable():
    provider = FakeVision("nope", "still nope")
    with pytest.raises(vlm.VlmUnusable):
        await vlm.observe(provider, b"x", model="m", label_map=LABELS)
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_quota_and_network_errors_are_not_retried_they_propagate():
    provider = FakeVision(RuntimeError("429 rate limited"), GOOD)
    with pytest.raises(RuntimeError):
        await vlm.observe(provider, b"x", model="m", label_map=LABELS)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_an_empty_answer_counts_as_unusable():
    provider = FakeVision("", GOOD)
    assert (await vlm.observe(provider, b"x", model="m", label_map=LABELS)).attempts == 2
