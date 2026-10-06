"""Hindi dose phrasings, written with Devanagari digits and in Hindi word order, through the real finalize.
Added with the UI-language hint (2026-10-06): once Hindi answers are asked for, a dose in Devanagari digits
("२५०") must meet exactly the same guards as one in ASCII digits."""
import pytest

from app.agent import finalize
from app.agent.tools.farm_context import FarmContextData
from app.safety import interim_dose_guard
from app.schemas.advisory import DraftAdvisory

FARM = FarmContextData(farm_name="F", crop_name="Tomato")
DOSES = [
    "प्रति एकड़ २५० मिली दवा डालें।",
    "२ ग्राम दवा प्रति लीटर पानी में मिलाएँ।",
    "१५ लीटर पानी में ३० मिली दवा मिलाकर छिड़कें।",
    "१० लीटर पानी में २० मिली मिलाएँ।",  # the amount comes after the water: not a pattern find_dose_statement knows
    "एक एकड़ के लिए ५०० ग्राम पर्याप्त है।",
    "दवा का छिड़काव करने के २१ दिन बाद कटाई करें।",
    "पंप में ३० ग्राम डालिए।",
    "टंकी में दो ढक्कन डाल दें।",
    "दवा २५० डालें।",
    "0.5% घोल बनाकर छिड़कें।",
    "०.५ प्रतिशत घोल बनाइए।",
    "छिड़काव के बाद ७ दिन रुकें, फिर तोड़ें।",
]
QUESTIONS = ["कितनी दवा डालूँ?", "क्या करूँ?"]


def run(recommendation: str, question: str):
    draft = DraftAdvisory(
        evidence_basis="farm_and_weather_data", citations=[], model_inference="सामान्य सलाह।",
        recommendation=recommendation, confidence=0.7, abstained=False, abstained_because=None,
    )
    return finalize.finalize_advisory(
        draft, farm_data=FARM, live_data=None, passages=[], named_crops=frozenset(), question_text=question
    )


@pytest.mark.parametrize("question", QUESTIONS)
@pytest.mark.parametrize("text", DOSES)
def test_a_hindi_dose_never_reaches_the_farmer(text, question):
    r = run(text, question)
    assert r.abstained and r.abstained_because == interim_dose_guard.SAFE_ABSTAIN_REASON
    assert text not in r.recommendation


@pytest.mark.parametrize("text", ["सुबह पानी दें और पत्तियाँ जाँचें।", "बुवाई को ३८ दिन हुए हैं।", "सीमा ५० मिमी है, अभी ४५ मिमी की कमी है।"])
def test_ordinary_hindi_advice_with_devanagari_digits_is_not_blocked(text):
    assert not run(text, "क्या करूँ?").abstained
