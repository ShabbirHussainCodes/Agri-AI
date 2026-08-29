# Architecture Diagrams

GitHub renders ```mermaid``` fences natively.

## Simple architecture

```mermaid
flowchart LR
  F["Farmer<br/>low-end Android"] -->|voice / photo / text| W["Next.js PWA<br/>UI + auth session"]
  W -->|HTTPS| API["FastAPI backend<br/>agent core + safety layer"]
  API --> DB[("Postgres<br/>farm data + pgvector")]
  API --> EXT["External APIs<br/>weather · mandi · soil"]
  API --> AI["AI providers<br/>Groq · local ONNX · Mistral"]
  API --> ST[("Supabase Storage<br/>crop photos")]
  CRON["Scheduled jobs<br/>GitHub Actions + Supabase Cron"] -.->|same entrypoints| API
```

## Detailed layers

```mermaid
flowchart TB
  subgraph CLIENT
    W["Next.js PWA · MediaRecorder voice · camera · Web Push · timeline · offline shell"]
  end
  subgraph APP["API & Application — FastAPI"]
    A1["JWT verify (JWKS)"] --- A2["Pydantic validation"] --- A3["rate limit"] --- A4["upload scan + resize"] --- A5["domain services"] --- A6["OTel"]
  end
  subgraph AI["Agent & AI Layer"]
    T["tool loop (hand-rolled)"]
    R["RAG pipeline<br/>hybrid + RRF + rerank"]
    V["vision pipeline<br/>ONNX + VLM + OOD"]
    S["speech pipeline<br/>Whisper + transcript UI"]
    SAFE["DETERMINISTIC SAFETY LAYER<br/>denylist · dose lookup · abstain"]
    P["provider abstraction<br/>Groq · local ONNX · Mistral"]
    T --- R --- V --- S --- SAFE --- P
  end
  subgraph DATA
    D1[("Postgres — farm + activity")]
    D2[("pgvector — chunks")]
    D3[("agrochemical label table")]
    D4[("price time-series")]
    D5[("Supabase Storage — photos")]
  end
  W --> APP --> AI --> DATA
```

## One request, end to end (two-call shape + safety gate)

```mermaid
sequenceDiagram
  participant U as Farmer
  participant API as FastAPI
  participant TA as Turn A (tools, streaming)
  participant TB as Turn B (strict schema, no tools)
  participant SG as Safety gate (code)
  U->>API: question (voice/text)
  API->>TA: gather evidence
  TA->>TA: get_farm_context · get_weather · search_knowledge · lookup_agrochemical
  TA-->>API: evidence bundle
  API->>TB: construct typed answer from evidence
  TB-->>SG: {structured_data, retrieved_evidence, model_inference, recommendation}
  SG->>SG: citation exists? · molecule allowed? · dose from table? · score above floor?
  alt passes
    SG-->>U: answer + evidence + confidence
  else fails
    SG-->>U: abstain → KVK / Kisan Call Centre 1800-180-1551
  end
  SG-->>API: write answer + evidence back to farm record
```

## Crop image pipeline

```mermaid
flowchart LR
  P["Photo"] --> Q{"Quality gate<br/>blur/dark/is-plant?"}
  Q -->|reject| RE["ask for a better photo"]
  Q -->|ok| C["ONNX classifier<br/>top-3 + OOD score"]
  C --> VL["VLM reasoning (Groq qwen)<br/>+ crop, stage, season, district, weather"]
  VL --> RG["RAG grounding<br/>TNAU/ICAR factsheets, cited"]
  RG --> SAFE["Deterministic layer<br/>denylist · CIB&RC dose + waiting period<br/>disagreement/OOD → abstain"]
  SAFE --> OUT["Farmer view:<br/>top-3 with bands · 'model saw' vs 'label says' · sources · not-sure state"]
```

## Feature dependency map

```mermaid
flowchart LR
  FM["Farm data model + auth + RLS"] --> TL["Tool loop + typed response"]
  PA["Provider abstraction"] --> TL
  EV["Eval set (before retriever)"] --> RAG["RAG retrieval"]
  CO["Corpus + licence register"] --> RAG
  TL --> WX["Weather advice"]
  TL --> RAG
  TL --> IMG["Image diagnosis"]
  TL --> MANDI["Mandi advisor (droppable)"]
  RAG --> SAFE["Safety layer"]
  IMG --> SAFE
  WX --> UI["Farm timeline UI"]
  RAG --> UI
  IMG --> UI
  MANDI --> UI
  TL --> VOICE["Voice layer"]
  UI --> ALERT["Alerts (Web Push) + scheduled jobs"]
```
