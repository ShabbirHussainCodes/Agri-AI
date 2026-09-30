"""Pure tests for app/safety/crop_scope.py (ADR-0014), plus the check that
ingest/sources.yaml only uses crop keys the lexicon knows."""
from pathlib import Path

import pytest
import yaml

from app.safety import crop_scope
from app.safety.crop_scope import crops_named_in

from ._chunks import make_chunk

SOURCES_YAML = Path(__file__).resolve().parents[3] / "ingest" / "sources.yaml"


@pytest.mark.parametrize("question, expected", [
    # unans-001, the case this module exists for.
    ("When should I sow wheat in Madhya Pradesh?", {"wheat"}),
    # Hinglish and Hindi, incl. both spellings of the nasal in gehun.
    ("Kya aaj mujhe apne gehun ko paani dena chahiye?", {"wheat"}),
    ("गेहूँ की बुवाई कब करें?", {"wheat"}),
    ("गेहूं की बुवाई कब करें?", {"wheat"}),
    ("धान की कौन सी किस्म पंजाब के लिए सबसे अच्छी है?", {"rice"}),
    # Hindi oblique plural.
    ("टमाटरों में कीट लगे हैं", {"tomato"}),
    ("How do I control pink bollworm in cotton?", {"cotton"}),
    ("Can I use Spinosad 45% SC on my brinjal?", {"eggplant"}),
    # Longest match: sweet potato is not also potato.
    ("Sweet potato kab lagayein?", {"sweet_potato"}),
    ("Plant tomatoes and wheat together?", {"tomato", "wheat"}),
])
def test_crops_are_detected(question, expected):
    assert crops_named_in(question) == expected


@pytest.mark.parametrize("question", [
    "How much annual rainfall does Mandla district receive?",
    "Is black cotton soil good for a kitchen garden?",  # a soil type, not cotton
    "100 gram khad kitna dalna hai?",                    # 'gram' is a unit here
    "आम तौर पर बारिश कब होती है?",                        # 'आम' = 'generally' here
    "Mandla mein monsoon ke time kaunse crops lagate hain kitchen garden mein?",
    "What is a Jal Kund used for?",
])
def test_no_crop_is_detected(question):
    assert crops_named_in(question) == frozenset()


def test_rootstock_species_is_not_the_crop_in_a_grafting_question():
    assert crops_named_in("Which eggplant rootstock performed best in the tomato trial?") == {"tomato"}
    assert crops_named_in("Where were the eggplant rootstock seeds sourced from?") == frozenset()
    # Without grafting context, eggplant IS the crop.
    assert crops_named_in("When should I plant eggplant?") == {"eggplant"}


def test_scoping_keeps_only_documents_covering_every_named_crop():
    tomato_trial = make_chunk("trial text", crops=("tomato",))
    kitchen = make_chunk("garden text", crops=("tomato", "okra"))
    unreviewed = make_chunk("unreviewed", crops=())
    chunks = [tomato_trial, kitchen, unreviewed]
    assert crop_scope.scope_passages(chunks, frozenset()) == chunks  # no crop named: untouched
    assert crop_scope.scope_passages(chunks, frozenset({"tomato"})) == [tomato_trial, kitchen]
    assert crop_scope.scope_passages(chunks, frozenset({"okra"})) == [kitchen]
    assert crop_scope.scope_passages(chunks, frozenset({"wheat"})) == []
    assert crop_scope.scope_passages(chunks, frozenset({"tomato", "wheat"})) == []


def _approved_items():
    register = yaml.safe_load(SOURCES_YAML.read_text(encoding="utf-8"))
    return [i for s in register["sources"] for i in (s.get("approved_items") or [])]


def test_every_approved_document_has_a_crop_scope_decision_with_known_keys():
    items = _approved_items()
    assert items, "no approved items found in sources.yaml"
    for item in items:
        assert "crops_covered" in item, f"{item['handle']}: no crops_covered decision"
        assert crop_scope.unknown_keys(item["crops_covered"] or []) == [], item["handle"]


def test_no_current_document_is_a_source_for_wheat():
    # The unans-001 guarantee, stated against the real register: if someone
    # later marks a document as covering wheat, this test makes them look.
    for item in _approved_items():
        assert "wheat" not in (item["crops_covered"] or []), item["handle"]


def test_every_lexicon_form_maps_to_exactly_one_crop():
    seen: dict[tuple[str, ...], str] = {}
    for key, forms in crop_scope.CROP_LEXICON.items():
        for form in forms:
            toks = tuple(crop_scope._tokens(form))
            assert toks, (key, form)
            assert seen.setdefault(toks, key) == key, f"{form!r} maps to {seen[toks]} and {key}"
