"""AdvisoryResponse: the agent's one and only output shape
(docs/api/api-contracts.md). Separates what came from our own DB
(structured_data), a live external API (live_data), retrieved documents
(retrieved_evidence), the model's own inference (model_inference), and the
final recommendation -- so it's always clear which part of an answer is a
fact vs a model guess (CLAUDE.md rule #3).

TWO SHAPES SINCE PHASE 4 (ADR-0013, which supersedes ADR-0006's "one
Pydantic model = LLM schema + response" clause):

  DraftAdvisory     -- what the MODEL writes in Turn B: its reasoning, its
                       recommendation, and bare citations {passage, quote}.
  AdvisoryResponse  -- what the FARMER receives, assembled by CODE
                       (app/agent/finalize.py) from the draft plus data the
                       model is never allowed to author: the farm record,
                       the weather result, and every piece of source
                       metadata (title, year, page, licence, URL).

Why split: with one shared model, the LLM wrote retrieved_evidence
(including source names and page numbers) and structured_data itself, and
code could only check them afterwards. With the split, provenance cannot be
fabricated because the model never produces it.

structured_data/live_data stay typed to the real tool output shapes
(FarmContextData, WeatherData), not a generic dict.

Phase 5 (ADR-0015) adds a third kind of evidence: `water_balance`, numbers
COMPUTED by code from the farm record, the weather and a reference table. It is
neither measured (live_data) nor the farm record (structured_data), so it has
its own field, and the model never writes it. DraftAdvisory gains one word,
`irrigation_verdict`, which code compares with the computed verdict.
"""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent.tools.farm_context import FarmContextData
from app.agent.tools.weather import WeatherData
from app.agronomy.water_balance import WaterBalanceResult
from app.retrieval.citations import Citation
from app.safety.agrochemical_lookup import LabelEntry


class EvidenceItem(BaseModel):
    """One retrieved passage that a VALIDATED citation points at. Every field
    except `quote` is copied by code from the chunk/document row."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    source_org: str | None
    doc_title: str
    doc_type: str
    published_year: int | None = None
    page: int | None = None
    licence: str
    url: str
    quote: str


class AdvisoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structured_data: FarmContextData
    live_data: WeatherData | None = None
    # ADR-0015: set only when get_irrigation_status ran. Written by code.
    water_balance: WaterBalanceResult | None = None
    # ADR-0016: verified label cards (dose, waiting period) copied by code from the
    # agrochemical table. The only place a dose reaches the farmer; empty on any abstention.
    agrochemical_label: list[LabelEntry] = []
    retrieved_evidence: list[EvidenceItem] = []
    model_inference: str
    recommendation: str
    confidence: float | None = None
    abstained: bool
    abstained_because: str | None = None
    # Set by code, never by the model: True when every citation the model
    # made was checked and verified against the passage it named.
    citations_valid: bool

    @field_validator("recommendation", "model_inference")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Backstop for the inj-003 bug: the farmer must never receive a blank
        answer. finalize_advisory fills every abstention with a message; this
        makes any future code path that forgets fail loudly instead."""
        if not value.strip():
            raise ValueError("must not be blank")
        return value


EvidenceBasis = Literal["retrieved_passages", "farm_and_weather_data", "none"]
IrrigationVerdict = Literal["irrigate_now", "wait", "cannot_assess", "not_applicable"]


class DraftAdvisory(BaseModel):
    """Turn B's strict output schema (Groq strict JSON mode). Kept small on
    purpose: fewer fields the model controls, fewer tokens, less to go wrong."""

    model_config = ConfigDict(extra="forbid")

    evidence_basis: EvidenceBasis = Field(
        description=(
            "What the answer rests on: 'retrieved_passages' if it uses anything from "
            "the retrieved passages (then citations are required), "
            "'farm_and_weather_data' if it uses only this farm's record, weather and "
            "irrigation status, "
            "'none' if nothing provided supports an answer."
        )
    )
    citations: list[Citation] = Field(
        description="One entry per claim taken from a passage: its [n] number and an exact quote."
    )
    model_inference: str
    recommendation: str
    confidence: float | None
    abstained: bool
    abstained_because: str | None
    # Default only so a payload written before Phase 5 still parses (the
    # recorded Phase 2 cassette); the schema sent to Groq lists every field
    # as required (providers/groq_provider.py _make_strict), so a live model
    # always writes it.
    irrigation_verdict: IrrigationVerdict = Field(
        default="not_applicable",
        description=(
            "Copy the 'verdict' of the get_irrigation_status result exactly. "
            "'not_applicable' if no such result was provided."
        ),
    )
