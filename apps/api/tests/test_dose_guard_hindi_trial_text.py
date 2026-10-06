"""A Hindi answer about a trial must not be read as a dose just because it says "mixed".

Found in the `--language hi` eval run of 2026-10-06 (evals/results/ui-language-2026-10-06.md): the model's own
`model_inference` for en-fact-001 and tab-003 (recorded drafts, copied here) contained "मिलाकर" / "मिलाया" and the
trial labels EG 203 and T4. The bare stem "मिला" made that an application sentence, the grounded-number rule counts
no corpus numbers, so a plain trial description was withheld as `no_verified_dose_source`. Instruction forms
(मिलाएँ, मिला दें, ...) must stay blocked; the existing Hindi dose tests cover them, the cases here pin the border."""
import pytest

from app.agent import finalize
from app.agent.tools.farm_context import FarmContextData
from app.safety import interim_dose_guard
from app.schemas.advisory import DraftAdvisory

FARM = FarmContextData(farm_name="F", crop_name="Tomato")

TRIAL_TEXTS = [  # (question, recorded model text)
    ("Which eggplant rootstock performed best when combined with IPDM practices in the Tamil Nadu tomato trial?",
     "अध्ययन के अनुसार, EG 203 जड़भित्ति IPDM के साथ मिलाकर उपयोग करने पर सभी परीक्षण स्थलों में सबसे अच्छा प्रदर्शन करती है।"),
    ("What does treatment T4 consist of in the tomato IPDM trial?",
     "T4 में Eggplant RS‑EG203‑ग्राफ़्टेड टमाटर को किसान की प्रथा (FP) के साथ मिलाया गया है।"),
]
# Same border, instruction side: every one of these must still be withheld.
STILL_BLOCKED = [
    "२० मिली दवा १० लीटर पानी में मिला दें।",
    "१० लीटर पानी में २० मिली मिलाएँ।",
    "२० मिली मिलाओ।",
    "पानी में ७५० मिलाना।",
    "पानी में 750 मिलाएं।",
]


def run(question: str, *, inference: str = "सामान्य सलाह।", recommendation: str = "सामान्य सलाह।"):
    draft = DraftAdvisory(
        evidence_basis="farm_and_weather_data", citations=[], model_inference=inference,
        recommendation=recommendation, confidence=0.7, abstained=False, abstained_because=None,
    )
    return finalize.finalize_advisory(
        draft, farm_data=FARM, live_data=None, passages=[], named_crops=frozenset(), question_text=question
    )


@pytest.mark.parametrize("question,text", TRIAL_TEXTS)
@pytest.mark.parametrize("field", ["inference", "recommendation"])
def test_a_trial_description_with_a_mixed_verb_is_not_a_dose(question, text, field):
    r = run(question, **{field: text})
    assert not r.abstained, r.abstained_because


@pytest.mark.parametrize("text", STILL_BLOCKED)
def test_the_instruction_forms_are_still_withheld(text):
    r = run("कितनी दवा डालूँ?", recommendation=text)
    assert r.abstained and r.abstained_because == interim_dose_guard.SAFE_ABSTAIN_REASON
