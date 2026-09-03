"""AdvisoryResponse: the agent's one and only output shape
(docs/api/api-contracts.md). Separates what came from our own DB
(structured_data), a live external API (live_data), retrieved documents
(retrieved_evidence -- always [] until Phase 3-4's RAG exists), the
model's own inference (model_inference), and the final recommendation --
so it's always clear which part of an answer is a fact vs a model guess
(CLAUDE.md rule #3).

structured_data/live_data are typed to the *real* tool output shapes
(FarmContextData, WeatherData), not a generic dict. This is deliberate:
Groq's strict JSON-schema mode (ADR-0004: "Strict JSON (Turn B) on
gpt-oss-120b") needs the full shape known in advance for constrained
decoding -- an open-ended dict can't be constrained that way. Tying
these fields to the tool schemas also means the final answer schema and
the tools that feed it can never silently drift apart.
"""
from pydantic import BaseModel, ConfigDict

from app.agent.tools.farm_context import FarmContextData
from app.agent.tools.weather import WeatherData


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_org: str
    doc_title: str
    published_year: int
    page: int | None = None
    quote: str


class AdvisoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structured_data: FarmContextData
    live_data: WeatherData | None = None
    retrieved_evidence: list[EvidenceItem] = []
    model_inference: str
    recommendation: str
    confidence: float | None = None
    abstained: bool
    abstained_because: str | None = None
    citations_valid: bool
