"""lookup_agrochemical: the model asks WHICH verified label rows exist; code
decides everything else (ADR-0016).

Unlike get_weather and get_irrigation_status this tool takes arguments from the
model (a crop, a pest, optionally a molecule), so they are validated and
normalised here: the crop must resolve to exactly one canonical crop key, and
nothing the model passes reaches a query, a path or a prompt unchecked.

The model is told ONLY that a label card exists, and for which molecule, crop
and pest. It is not given a dose, a dilution, a waiting period or even the
formulation string (which carries a percentage): a model that never saw the
numbers cannot leak or garble them, and anything dose-shaped it writes anyway is
blocked by the guards in finalize. The numbers travel in `LabelEntry`, copied by
code into the farmer's response.

The tool is offered only when the question has chemical vocabulary
(`question_is_chemical`), to keep its tokens off every other question.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.safety import chemical_guard, crop_scope
from app.safety.agrochemical_lookup import (
    NO_VERIFIED_ENTRY,
    AgrochemTable,
    LabelEntry,
    entry_from_row,
    get_table,
    lookup,
)

TOOL_NAME = "lookup_agrochemical"
MAX_ARG_CHARS = 80

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Check whether a verified pesticide label entry exists for a crop and a pest "
            "(optionally a named molecule). If one exists the system itself shows the farmer a label "
            "card with the dose and waiting period: you never write those. Use it when the farmer asks "
            "what to spray or how much."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "The crop, e.g. tomato."},
                "pest": {"type": "string", "description": "The pest or disease, e.g. early blight."},
                "molecule": {"type": "string", "description": "Optional: a specific pesticide molecule the farmer named."},
            },
            "required": ["crop", "pest"],
            "additionalProperties": False,
        },
    },
}

def question_is_chemical(question: str, denylist: chemical_guard.Denylist) -> bool:
    """True if the question talks about chemicals or names a listed molecule."""
    return chemical_guard.is_chemical_text(question, denylist)


@dataclass
class LookupOutcome:
    payload: dict[str, Any]  # what the model reads: never a number
    entries: list[LabelEntry] = field(default_factory=list)  # what the farmer's card shows


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if 0 < len(value) <= MAX_ARG_CHARS else None


def run_lookup(
    arguments: dict[str, Any], *, table: AgrochemTable, denylist: chemical_guard.Denylist
) -> LookupOutcome:
    crop_arg, pest, molecule = _clean(arguments.get("crop")), _clean(arguments.get("pest")), arguments.get("molecule")
    molecule = _clean(molecule) if molecule not in (None, "") else None
    if crop_arg is None or pest is None or (arguments.get("molecule") not in (None, "") and molecule is None):
        return LookupOutcome({"status": "error", "reason": "invalid_arguments"})
    crops = crop_scope.crops_named_in(crop_arg)
    if len(crops) != 1:
        return LookupOutcome({"status": "not_found", "reason": "crop_not_recognised"})
    if molecule and chemical_guard.find_banned([molecule], denylist):
        # The farmer-facing refusal is written by finalize; the model just learns there is nothing to show.
        return LookupOutcome({"status": "not_found", "reason": "molecule_not_permitted"})

    (crop,) = crops
    rows, reason = lookup(table, denylist, crop=crop, pest=pest, molecule=molecule)
    if not rows:
        return LookupOutcome({"status": "not_found", "reason": reason or NO_VERIFIED_ENTRY})
    entries = [entry_from_row(r, table.table_version) for r in rows]
    return LookupOutcome(
        {
            "status": "found",
            "entries": [{"molecule": r.molecule, "crop": r.crop, "pest": r.pest} for r in rows],
            "instruction": (
                "The system will show the farmer a label card with the dose and waiting period. "
                "Do not write any dose, rate, dilution or waiting period yourself; refer to the card."
            ),
        },
        entries,
    )


def table_for(path: Path | None) -> AgrochemTable:
    return get_table(path)
