"""The frozen world the Phase 5 irrigation eval runs in (ADR-0015).

Live weather is not reproducible, so every scenario in
evals/irrigation_scenarios.jsonl describes its own weather, farm and irrigation
log, and this module turns that description into the same shapes the real
tool reads: database rows (FakeConn), an Open-Meteo series (make_fetch) and a
clock (FROZEN_NOW). Nothing here touches a database or a network.

What is real when the eval runs: the agent loop, the tool, the water-balance
engine, finalize and the guards, and (with --live) the Groq model.
What is not: the reference table is SYNTHETIC (evals/fixtures/), retrieval
returns no passages, and the weather is invented. So the eval measures the
PIPELINE (does the farmer see what code computed, are numbers grounded, does it
abstain when inputs are missing), never agronomic accuracy (CLAUDE.md rule 4).
Retrieval returning nothing is faithful for wheat and maize, which no ingested
document covers (ADR-0014); for tomato the real pipeline would also show corpus
passages, so a tomato scenario understates tokens by up to the passage block.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.agent.tools.farm_context import ActivitySummary, FarmContextData
from app.agronomy.water_balance import DayWeather
from app.integrations.open_meteo import DailySeries, OpenMeteoError
from app.providers.base import ChatResult, LLMProvider, ToolCall

EVALS = Path(__file__).resolve().parent
FIXTURE_TABLE = EVALS / "fixtures" / "crop_water_synthetic.json"
SCENARIOS = EVALS / "irrigation_scenarios.jsonl"

FROZEN_NOW = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)  # 11:30 IST
UTC_OFFSET_SECONDS = 19800
FROZEN_TODAY = (FROZEN_NOW + timedelta(seconds=UTC_OFFSET_SECONDS)).date()  # 2026-10-10
PAST_DAYS = 92
FORECAST_DAYS = 7


def load_scenarios() -> list[dict[str, Any]]:
    return [json.loads(line) for line in SCENARIOS.read_text(encoding="utf-8").splitlines() if line.strip()]


def days_ago(n: int) -> date:
    return FROZEN_TODAY - timedelta(days=n)


def irrigation_events(scenario: dict) -> list[dict]:
    """Rows as the activities query would return them, oldest first."""
    rows = []
    for ev in scenario["irrigations"]:
        details = {} if ev["depth_mm"] is None else {"depth_mm": ev["depth_mm"]}
        rows.append({"occurred_on": days_ago(ev["days_ago"]), "details": details})
    return sorted(rows, key=lambda r: r["occurred_on"])


class FakeConn:
    """Answers the three queries get_irrigation_status makes."""

    def __init__(self, scenario: dict):
        self.s = scenario

    async def fetchrow(self, sql: str, *args):
        if "public.farms" in sql:
            loc = self.s["location"]
            return {"lat": 26.85 if loc else None, "lon": 80.95 if loc else None, "soil_texture": self.s["soil"]}
        if "public.farm_crops" in sql:
            return {"id": "eval-crop", "name_en": self.s["crop"], "sowing_date": days_ago(self.s["sowing_days_ago"])}
        raise AssertionError(f"unexpected query: {sql}")

    async def fetch(self, sql: str, *args):
        return irrigation_events(self.s)


def farm_context_for(scenario: dict) -> FarmContextData:
    """What get_farm_context would return, with `days_since_sowing` computed
    from the frozen date (the real one uses the machine's date)."""
    sowing = days_ago(scenario["sowing_days_ago"])
    recent = sorted(irrigation_events(scenario), key=lambda r: r["occurred_on"], reverse=True)[:5]
    return FarmContextData(
        farm_name="Eval Farm",
        crop_name=scenario["crop"],
        sowing_date=sowing,
        days_since_sowing=scenario["sowing_days_ago"],
        recent_activities=[
            ActivitySummary(type="irrigation", occurred_on=r["occurred_on"], details=json.dumps(r["details"]))
            for r in recent
        ],
    )


def build_series(scenario: dict) -> DailySeries:
    w = scenario["weather"]
    rain_by_days_ago = {int(k): v for k, v in w["rain_mm_by_days_ago"].items()}
    days: list[DayWeather] = []
    for n in range(PAST_DAYS, 0, -1):  # 92 observed days: today-92 .. yesterday
        days.append(DayWeather(date=days_ago(n), et0_mm=w["et0_mm"], rain_mm=rain_by_days_ago.get(n, 0.0)))
    for k in range(FORECAST_DAYS):  # today .. today+6
        rain = w["forecast_rain_mm"][k] if k < len(w["forecast_rain_mm"]) else 0.0
        days.append(DayWeather(date=FROZEN_TODAY + timedelta(days=k), et0_mm=w["forecast_et0_mm"], rain_mm=float(rain)))
    return DailySeries(utc_offset_seconds=UTC_OFFSET_SECONDS, days=days)


def make_fetch(scenario: dict):
    async def fetch(lat, lon, **kw):
        if scenario["weather"].get("unavailable"):
            raise OpenMeteoError("scenario: weather service is down")
        return build_series(scenario)

    return fetch


class DryRunProvider(LLMProvider):
    """A scripted stand-in for the model, used by the default (no-quota) run
    and by the tests: calls the irrigation tool, then writes a correct answer
    that copies the computed numbers. Measures the harness, not a model."""

    async def chat(self, messages, *, model, tools=None, response_schema=None):
        if response_schema is None:
            if not any(m.get("role") == "tool" for m in messages):
                return ChatResult(tool_calls=[ToolCall(id="c1", name="get_irrigation_status", arguments={})])
            return ChatResult(content="enough")
        wb = next((json.loads(m["content"]) for m in messages if m.get("role") == "tool"), {})
        verdict = wb.get("verdict", "not_applicable")
        if verdict in ("irrigate_now", "wait"):
            text = f"The soil is short of {wb['depletion_mm']} mm; the limit is {wb['raw_mm']} mm."
        else:
            text = "I cannot work this out."
        return ChatResult(content=json.dumps({
            "evidence_basis": "farm_and_weather_data", "citations": [],
            "model_inference": "Based on the computed irrigation status.",
            "recommendation": text, "confidence": 0.7, "abstained": False,
            "abstained_because": None, "irrigation_verdict": verdict,
        }))
