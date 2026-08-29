# Multimodal / Crop-Image Diagnosis

> Governing rule: **never promise an accuracy figure.** Accuracy is a measured evaluation output. The architecture optimises for honest field evaluation and reliable abstention, not a headline number. (`CLAUDE.md` §4.)

## 1. Why the hybrid shape

Evidence we are designing around: a PlantVillage-trained classifier can score ~99% in the lab and collapse on real field photos while keeping high confidence, and general VLMs are better at *explaining* a named disease than at *seeing* it. So: let a small classifier *see*, let the VLM *explain*, let RAG *ground*, and let deterministic code *decide* whether any dose may be stated.

## 2. Pipeline (three provider stages, by necessity)

Groq's vision model (`qwen/qwen3.6-27b`) does not support strict schema, structured outputs can't combine with tools, and prompt caching doesn't apply to it. So diagnosis is staged, not one call:

```
1. Quality gate (code)      blur / dark / "is this a plant?" → reject early, ask for a better photo
2. ONNX classifier (CPU)    top-3 candidates + OOD / max-logit score      [MIT ViT-tiny]
3. VLM reasoning (Groq)     qwen3.6-27b + crop, stage, season, district, weather ; plain JSON mode
4. RAG grounding            authoritative factsheets, cited
5. Deterministic layer      banned-molecule denylist · CIB&RC dose + waiting period (verbatim)
                            · classifier/VLM disagreement OR OOD fires → ABSTAIN
6. Answer construction      separate strict-schema call (gpt-oss-120b) → evidence-typed object
```

## 3. Presenting uncertainty (required behaviours)

- **Top-3, never top-1.** Top-1 framing is where misinformation enters.
- **No raw softmax shown as "confidence."** If a number is shown, it is calibrated and we say on what.
- **Abstention is a feature.** OOD / disagreement → "this doesn't look like something I can identify — contact your KVK / Kisan Call Centre 1800-180-1551." Demo it deliberately.
- On screen, separate **what the model saw** from **what the label says** from the **final recommendation**.

## 4. Evaluation (Phase 7)

- Evaluate on **field-condition** images (e.g. PlantDoc, CC-BY-4.0) and Indian field datasets — **never** PlantVillage as the eval set.
- Report **cross-domain** accuracy as the headline, plus calibration (ECE) and abstention rate.
- Note dataset licences: PlantVillage for pretraining only; PlantWild is CC-BY-NC-ND (no derivatives — academic eval only).

## 5. Safety linkage

No LLM and no VLM ever emits a pesticide dose. Any chemical recommendation that survives to the farmer carries a verbatim, dated CIB&RC label entry via the deterministic layer, or the system abstains. See `docs/security/security-model.md` and `docs/decisions/ADR-0005-*`.

## 6. Privacy linkage

Farmer photos may go to Groq specifically because Groq's terms prohibit training on inputs and treat them as confidential (ADR-0004). They must not be routed to any provider whose free tier trains on inputs or allows human review.
