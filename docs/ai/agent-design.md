# Agent Design

> The agent is a **hand-rolled tool-calling loop** (ADR-0002). Pydantic AI is a *later* migration option only if a real need (durable retries, HITL approval, richer eval harness) appears. No LangGraph/CrewAI on day one.

## 1. Responsibilities

The agent has one job: given a farmer's question and their farm, gather the right evidence with tools, then hand a clean evidence bundle to the answer step. It does **not** own safety decisions (the deterministic layer does) and it does **not** silently mutate the farm record.

## 2. The loop (conceptual)

```
messages = [system_prompt, user_turn(+farm_id)]
loop (bounded, max N tool rounds):
    response = LLM(messages, tools=READ_TOOLS)   # Turn A: streaming, no strict schema
    if response.tool_calls:
        for call in response.tool_calls:
            result = dispatch(call)               # validated inputs, typed outputs
            messages.append(tool_result(result))
    else:
        break
evidence = collect(messages)
answer = LLM(evidence, schema=AdvisoryResponse)  # Turn B: strict schema, no tools
return safety_layer(answer)                       # deterministic, runs last
```

`N` is bounded (every extra round costs a real slice of the free-tier token budget). Agency is used only for routing, genuine multi-hop, and a single corrective retry.

## 3. Tools

| Tool | Kind | Input | Output |
|---|---|---|---|
| `get_farm_context` | read | `farm_id` | crop, variety, sowing date, computed stage, area, soil card values, last N activities |
| `get_weather` | read | none (farm-bound) | Phase 2 subset: current temp and rain + 3-day rain forecast. The fuller forecast in the original spec was not built; irrigation uses `get_irrigation_status` instead |
| `get_irrigation_status` | read | none (farm-bound) | computed FAO-56 root-zone water balance for the active crop: `verdict`, `depletion_mm`, `raw_mm`, `days_to_raw`, assumptions, or `cannot_assess` with a reason (ADR-0015) |
| `search_knowledge` | read | `query, crop, state, stage, language` | ranked chunks + source + year + page |
| `lookup_agrochemical` | read | `crop, pest, [molecule]` | offered only to chemical questions (ADR-0016). Returns to the model **no numbers**: only whether a verified label entry exists (`found` + molecule/crop/pest, or `not_found`). Code puts the dose, dilution and **waiting period** in the response's `agrochemical_label` card |
| `get_market_price` | read | `commodity, district, days` | modal-price series + arrivals + percentile band |
| `analyze_crop_image` | — | — | **Not an agent tool.** A photo is a separate pipeline with its own endpoint (`POST /farms/{id}/scans`, `app/vision/`, ADR-0018): its deterministic stages decide before any model writes a word, and only then does the same answer step and safety stack as `/ask` run. The agent loop never sees a photo |
| `log_activity` | **write** | `farm_id, type, date, details` | `activity_id` |
| `create_reminder` | **write** | `farm_id, when, message` | `reminder_id` |

**Every tool:** validated inputs (Pydantic), typed outputs, explicit error handling, no unbounded permissions.

**Write tools require explicit user confirmation.** The agent proposes; the farmer confirms; only then does the write happen. The agent never edits the farm record on its own.

## 4. Deterministic vs LLM (the boundary)

| Task | Owner | Why |
|---|---|---|
| Pesticide dose & waiting period | **code** | safety — a hallucinated number is real harm |
| Banned-molecule check | **code** | legal / must be deterministic |
| Days-after-sowing, growth stage | **code** | date math |
| Irrigation need (ET₀ − rainfall) | **code**, LLM explains | FAO-56 is a formula. Code also checks the model's verdict and every number it states against what code computed (`app/safety/irrigation_guard.py`, ADR-0015) |
| Price percentile / trend | **code** | statistics |
| Retrieval confidence floor / abstention | **code** | cheap, deterministic, runs before the LLM |
| Citation validation | **code** | reliable fabrication check |
| Intent, query rewriting, explanation | **LLM** | language understanding |
| Multi-factor reasoning & trade-offs | **LLM** | genuine reasoning value |

## 5. Prompt-injection posture

Corpus text is untrusted: delimited, never able to trigger tools, and the safety layer runs *after* generation so injected instructions can't reach the dose lookup or denylist. Injection cases live in the eval set.

## 6. Migration trigger to Pydantic AI

Adopt Pydantic AI only when we actually need durable retries, human-in-the-loop approval on advisory outputs, or its eval harness — and record the switch in a new ADR. It supports Groq as a first-class provider and covers the same fallback ladder, so the migration is a string-swap, not a rewrite.
