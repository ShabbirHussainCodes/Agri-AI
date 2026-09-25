"""Pure unit tests for the INTERIM dose/waiting-period guard.

Positives come from the real corpus and eval set (the trial protocol's
rates, the dose-bucket questions). Negatives are the reference answers of
ANSWERABLE eval questions that contain numbers -- the guard must not block
legitimate answers the eval expects."""
import pytest

from app.safety.interim_dose_guard import find_dose_statement

MUST_BLOCK = [
    "Apply B. subtilis @ 4 g/L at transplanting.",
    "Tilt® 25% EC @ 1 mL/L was sprayed.",
    "Use Beauveria bassiana at 5 ml per litre.",
    "Mix 10 ml in 10 litres of water and spray.",
    "Apply 2 kg/ha of the granules.",
    "The recommended dose is 2 kg.",
    "4 ग्राम प्रति लीटर पानी में मिलाकर छिड़काव करें।",
    "इमिडाक्लोप्रिड की मात्रा 5 मिली रखें।",
    "Observe a waiting period of 14 days.",
    "Stop spraying 7 days before harvest.",
    "PHI: 3 days for tomato.",
    "कटाई से पहले 10 दिन तक छिड़काव न करें।",
]

MUST_ALLOW = [
    "About 1,300 millimetres a year, most of it concentrated in just three to four monsoon months.",
    "Nearly 88 per cent of the cultivated area is rainfed.",
    "About 350 to 450 square metres, divided into eight to fifteen raised beds roughly one metre wide.",
    "Transplanted on 26 September 2022, with an experiment area of 1,860 square metres.",
    "At 45, 60, 75, 90, 120 and 135 days after transplanting (DAT).",
    "EG 203 and TS 03.",
    "T1 > T3 > T6 > T2 > T4 > T5.",
    "लगभग 1,300 मिलीमीटर, जिसका अधिकांश हिस्सा केवल तीन से चार मानसून महीनों में पड़ता है।",
    "लगभग 88 प्रतिशत खेती वाला क्षेत्र वर्षा आधारित है।",
    "About two months: the rootstocks were seeded on 29 July 2022.",
    "Your farm is 1.5 ha and was sown 40 days ago.",
]


@pytest.mark.parametrize("text", MUST_BLOCK)
def test_blocks_doses_and_waiting_periods(text):
    assert find_dose_statement(text) is not None


@pytest.mark.parametrize("text", MUST_ALLOW)
def test_allows_numbers_that_are_not_doses(text):
    assert find_dose_statement(text) is None
