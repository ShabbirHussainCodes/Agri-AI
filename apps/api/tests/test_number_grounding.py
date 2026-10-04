"""Which numbers in a text are not in the evidence (app/safety/number_grounding.py).
Pure tests: no database, no network, no LLM."""
import pytest

from app.safety.number_grounding import numbers_in, ungrounded_numbers


@pytest.mark.parametrize(
    "text, expected",
    [
        ("50 mm", {50.0}),
        ("depletion 45.3 of 50.0", {45.3, 50.0}),
        ("about 1,200 mm a year", {1200.0}),  # thousands separator: one number
        ("on 5,6 days", {5.0, 6.0}),  # a list, not one number
        ("2026-10-08", {2026.0, 10.0, 8.0}),
        ("08.10.2026", {8.0, 10.0, 2026.0}),
        ("30-40 mm", {30.0, 40.0}),
        ("३० मिमी", {30.0}),  # Devanagari digits
        ("2.5 और ४", {2.5, 4.0}),
        ("no numbers here", set()),
        # Not numbers: a digit glued to a letter before it, and list markers.
        ("ET0 and H2O", set()),
        ("1. water\n2) wait\n 3. rest", set()),
        ("1. water 30 mm", {30.0}),
    ],
)
def test_numbers_in(text, expected):
    assert numbers_in(text) == expected


def test_a_number_the_evidence_contains_is_grounded_whatever_its_format():
    evidence = ['{"depletion_mm": 45.0, "raw_mm": 50.0, "days_to_raw": 3}']
    assert ungrounded_numbers(["The soil is short of 45 mm; the limit is 50 mm; 3 days."], evidence) == []


def test_an_invented_number_is_reported():
    evidence = ['{"depletion_mm": 45.0, "raw_mm": 50.0}']
    assert ungrounded_numbers(["Give 35 mm today."], evidence) == [35.0]


def test_a_rounded_paraphrase_is_reported_not_forgiven():
    # Fails safe on purpose: the model is told to copy the numbers exactly.
    assert ungrounded_numbers(["about 12 mm"], ['{"x": 12.4}']) == [12.0]


def test_the_farmers_own_number_may_be_repeated_back():
    assert ungrounded_numbers(["You irrigated 20 mm yesterday."], ["I irrigated 20 mm yesterday, what now?"]) == []


def test_the_helpline_number_is_always_allowed():
    assert ungrounded_numbers(["Call the Kisan Call Centre on 1800-180-1551."], []) == []


def test_every_text_is_checked_and_results_are_sorted():
    assert ungrounded_numbers(["7 mm", "3 days"], ["{}"]) == [3.0, 7.0]


def test_a_date_in_the_answer_is_grounded_by_a_date_in_the_evidence():
    assert ungrounded_numbers(["Last irrigation was on 5 October."], ['{"last_irrigation_on": "2026-10-05"}']) == []
