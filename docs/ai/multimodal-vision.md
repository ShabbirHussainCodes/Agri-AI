# Multimodal / Crop-Image Diagnosis

> Governing rule: **never promise an accuracy figure.** Accuracy is a measured evaluation output. The architecture optimises for honest field evaluation and reliable abstention, not a headline number. (`CLAUDE.md` §4.) The design is recorded in [ADR-0018](../decisions/ADR-0018-photo-diagnosis-pipeline.md); the numbers are in `evals/results/vision-*.md`.

## 1. Why the hybrid shape

Evidence we are designing around: a PlantVillage-trained classifier can score ~99% in the lab and collapse on real field photos while keeping high confidence, and general VLMs are better at *explaining* a named disease than at *seeing* it. So: let a small classifier *see*, let a second, independent model *check*, let RAG *ground*, and let deterministic code *decide* whether any dose may be stated, and whether anything may be said at all.

## 2. Pipeline (built in Phase 7)

```
0. Upload sanitising (code)  magic-byte type, size and pixel caps, decode, EXIF orientation then ALL metadata dropped,
                             downscale to 1024 px, re-encode as JPEG        app/vision/imaging.py
1. Quality gate (code)       size / blur / dark / washed out / "no leaf-coloured pixel at all"  -> "take a better photo"
                                                                            app/vision/quality.py
2. ONNX classifier (CPU)     DINOv2-small + linear head, 38 PlantVillage classes, top-3, calibrated probability,
                             OUT-OF-DISTRIBUTION score; refuses: not a leaf it knows / not sure / a crop AgriAI does
                             not have / a crop no field measurement qualified    app/vision/classifier.py, decision.py
   ---- only a photo that passed 0, 1 and 2 leaves the server ----
3. Vision model (Groq)       qwen/qwen3.8-27b, JSON mode, CLOSED vocabulary, blind to the classifier and the farm;
                             must name the SAME crop and condition as the classifier's top choice   app/vision/vlm.py
   Farm-crop check (code)    two models agreeing on a crop other than the farm record's -> refused (crop_differs_from_farm)
4. RAG grounding             hybrid retrieval scoped to the diagnosed crop (ADR-0014), verbatim-quote citations
5. Deterministic layer       label card for (crop, condition) looked up by CODE from the verified table;
                             banned-molecule denylist; dose guard; any abstention = no diagnosis shown
6. Answer construction       strict-schema answer call (gpt-oss-120b) -> finalize_advisory, the same stack as /ask
                                                                            app/vision/diagnose.py, answer.py
```

The two-stage decision (`decide_before_second_opinion`, `decide_with_second_opinion`) is a pure function of plain values, so each refusal is a unit test: `quality_rejected`, `out_of_distribution`, `low_confidence`, `crop_not_supported`, `crop_not_validated`, `not_a_plant_photo`, `model_disagreement` (sub-reasons `crop_unclear`, `crop_differs`, `condition_unclear`, `condition_differs`), `crop_differs_from_farm`, `vision_unavailable`, `vision_not_calibrated`, plus whatever the answer step refuses with (`invalid_citation`, `banned_molecule`, `no_verified_dose_source`, `injection_attempt`, `answer_generation_failed`).

## 3. Presenting uncertainty (required behaviours, as built)

- **Top-3, never top-1.** The agreed estimate comes first; the other two are shown as "it could also be".
- **No raw softmax shown as "confidence."** The farmer sees a *band* (high / medium / low) and, in words, what that band scored on field photos in our own measurement, on how many photos and what they were. `candidates[].probability` is in the API for the evals, not on screen.
- **Abstention is a feature, not an error.** A calm card, in code's own words, that says what to do (a clearer close-up, the KVK, the Kisan Call Centre 1800-180-1551). Five different stages can produce it. The demo shows it on purpose.
- On screen, **what the models saw** (the estimate and the vision model's one sentence), **what the label says** (the label card and the cited documents) and **the recommendation** are separate cards, and a diagnosis always carries "an automatic check, not an expert's confirmation".

## 4. Evaluation (Phase 7)

The protocol was written before any photo was classified (`evals/vision/README.md`) and is not edited after the first result. Field-condition photos only: PlantDoc (CC-BY-4.0) for in-label-space photos, rice and bean leaves for crops the model has no class for, objects for non-plants; **never PlantVillage as the evaluation set**. Calibration and test splits are disjoint. Reported with bootstrap intervals: cross-domain top-1 and top-3 accuracy, expected calibration error, out-of-distribution false-accept rates and AUROC, the quality gate's false-reject and detection rates, and, on a small subset because of the vision model's free-tier limits, how often the second model agrees and how precise the agreeing pair is. Results: `evals/results/vision-<date>.md`, `evals/results/vision-pipeline-<date>.md`.

Dataset licences: PlantVillage for pretraining only (the classifier's own training data); PlantWild is CC-BY-NC-ND (no derivatives — academic eval only) and was not used.

## 5. Safety linkage

No LLM and no VLM ever emits a pesticide dose. Any chemical recommendation that survives to the farmer carries a verbatim, dated CIB&RC label entry via the deterministic layer (ADR-0016), looked up by code from the diagnosed crop and condition, or the system abstains. The vision model's free text is dose- and banned-molecule-guarded before display. See `docs/security/security-model.md` and `docs/decisions/ADR-0005-*`.

## 6. Privacy linkage

Farmer photos may go to Groq specifically because Groq's terms prohibit training on inputs and treat them as confidential (ADR-0004). They must not be routed to any provider whose free tier trains on inputs or allows human review. The photo is stripped of EXIF before anything sees it, goes to Groq only after the local checks pass, is stored (if at all) in a private bucket under the farmer's own session, and can be deleted by the farmer.

## 7. What was measured, in one paragraph

On field photos (PlantDoc test, 225 photos) the model's published head got 41.8 % top-1 and qualified no crop; the head trained here on the frozen backbone got 64.4 % (95 % interval 58.2 to 70.7), top-3 87.6 %, and accepts 36 % of photos at 86.6 % accuracy; confidence bands held on the test photos. **Only maize qualified**; tomato (43.9 %), potato and soybean did not. The classifier stage accepts rice leaves 21 % of the time (it has no rice class), so the second model and the farm-crop check carry that case; in a live subset 1 of 8 rice photos still became a wrong diagnosis before the farm-crop rule existed. The second model names the crop right 30 of 36 times but the exact condition only 17 of 36. Details and limits: `evals/results/vision-2026-10-10.md`, `evals/results/vision-pipeline-2026-10-10.md`, ADR-0018.

## 8. What is not built

Wheat, rice, millets, cotton and pulses have **no** photo check (the classifier has no class for them, and no open, documented field-photo model for them could be validated); they abstain. A photo-based "which crop is this" is not offered. Voice, mandi prices and push are later phases.
