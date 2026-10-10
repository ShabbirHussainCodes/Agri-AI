"""The photo-diagnosis pipeline, end to end (ADR-0018, docs/ai/multimodal-vision.md).

    sanitised photo
      -> quality gate                  (code)           refuse: "take a better photo"
      -> ONNX classifier + OOD check   (CPU, local)     refuse: not a leaf we know, not sure, crop unknown/unmeasured
      -> vision-language model         (Groq, closed vocabulary, blind to the classifier)
      -> agreement                     (code)           refuse: the two disagree, or not a plant
      -> retrieval + label card        (code)           same grounding as /ask; the dose comes only from a verified row
      -> answer model                  (Groq, strict schema, no tools)
      -> finalize_advisory             (code)           the /ask safety stack: citations, crop scope, banned
                                                        molecule, dose guard

Each early exit returns a DiagnosisResponse with no model text in it: every sentence of a refusal is
written by code (app/vision/messages.py). The photo goes to the vision provider only after the local
checks pass, so a photo that will be refused anyway never leaves this server.

`diagnose` returns a DiagnosisRun: the response the farmer gets plus what each stage saw, for the eval
harness (evals/vision) and for the saved scan row.
"""
import logging
from dataclasses import dataclass
from pathlib import Path

import asyncpg
from fastapi.concurrency import run_in_threadpool

from app.agent.finalize import GENERATION_FAILED, GENERATION_FAILED_MESSAGE, abstain_message_for, finalize_advisory
from app.agent.loop import NO_SIMILARITY_GATE, TURN_B_LANGUAGE_RULES, GenerationFailed, _draft_retrying
from app.agent.tools import farm_context
from app.core.config import settings
from app.core.errors import AgentError
from app.providers.base import LLMProvider, TokenUsage, VisionProvider
from app.retrieval.context import build_passage_block
from app.retrieval.embedder import get_query_embedder
from app.retrieval.hybrid import Embedder, retrieve
from app.safety import agrochemical_lookup, chemical_guard, crop_scope, interim_dose_guard
from app.safety.agrochemical_lookup import LabelEntry
from app.schemas.advisory import AdvisoryResponse
from app.schemas.scan import (
    ConfidenceBand,
    DiagnosisResponse,
    ModelSaw,
    ModelVersions,
    QualityInfo,
    ScanCandidate,
)
from app.vision import decision, messages, quality, vlm
from app.vision.answer import SCAN_TURN_B_PROMPT, ScanDraft, scan_user_message
from app.vision.calibration import Calibration
from app.vision.classifier import Classifier, Prediction
from app.vision.imaging import PreparedImage
from app.vision.labels import LabelMap

logger = logging.getLogger("agriai.vision")

SCAN_LABEL_RULE = (
    "\n- The system will show the farmer a verified pesticide label card with the dose and waiting period. "
    "Never write a dose, rate, dilution, percentage or waiting period yourself, and do not abstain just because "
    "the card exists: say the card has the details and that the label on the product pack is the legal source."
)


@dataclass
class VisionDeps:
    """Everything a scan needs that is not the photo or the farm. Built once per process in
    app/vision/runtime.py; tests pass fakes."""

    classifier: Classifier | None  # None = the model file or its calibration is unusable: fail closed
    calibration: Calibration | None
    label_map: LabelMap
    vision: VisionProvider
    llm: LLMProvider
    vlm_model: str
    llm_model: str
    denylist: chemical_guard.Denylist
    quality_thresholds: quality.QualityThresholds
    embedder: Embedder | None = None
    agrochem_table: Path | None = None


@dataclass
class DiagnosisRun:
    response: DiagnosisResponse
    prediction: Prediction | None = None
    observation: vlm.VlmObservation | None = None
    vlm_usage: TokenUsage | None = None
    vlm_attempts: int = 0
    verdict: decision.Verdict | None = None
    answer_called: bool = False


def _quality_info(report: quality.QualityReport) -> QualityInfo:
    m = report.metrics
    return QualityInfo(
        passed=report.passed,
        reasons=list(report.reasons),
        thresholds_version=report.thresholds_version,
        sharpness=round(m.sharpness, 2),
        mean_luma=round(m.mean_luma, 2),
        vegetation_fraction=round(m.vegetation_fraction, 4),
        width=m.width,
        height=m.height,
    )


def _versions(deps: VisionDeps, *, vision_used: bool) -> ModelVersions:
    cal = deps.calibration
    return ModelVersions(
        classifier=(cal.model.get("repo", "unknown") + "@" + cal.model.get("revision", "unknown")[:12]) if cal else "unavailable",
        calibration=cal.version if cal else "unavailable",
        label_map=deps.label_map.version,
        vision_model=deps.vlm_model if vision_used else None,
    )


def _refusal(
    verdict: decision.Verdict, info: QualityInfo, versions: ModelVersions, *, message: str | None = None
) -> DiagnosisResponse:
    if verdict.outcome == "rejected_quality":
        text = messages.quality_message(info.reasons)
    else:
        text = message or messages.ABSTAIN_MESSAGES.get(verdict.reason or "", messages.ABSTAIN_MESSAGES[decision.LOW_CONFIDENCE])
    return DiagnosisResponse(
        outcome=verdict.outcome,
        abstained_because=verdict.reason,
        detail=verdict.detail,
        message=text,
        quality=info,
        versions=versions,
    )


def _guard_free_text(text: str, deps: VisionDeps) -> str:
    """The vision model's one sentence is shown to the farmer, so it passes the same guards as any
    farmer-facing text: no dose-shaped statement and no listed molecule. A text that trips either is
    dropped whole (the structured findings still stand)."""
    if not text:
        return ""
    if interim_dose_guard.find_dose_statement(text) or chemical_guard.find_banned([text], deps.denylist):
        logger.warning("vision model text dropped by the dose or banned-molecule guard")
        return ""
    return text


def _label_cards(leading_crop: str, pest: str | None, deps: VisionDeps) -> list[LabelEntry]:
    """Verified label rows for the diagnosed crop and condition, looked up by CODE. No row, no card."""
    if pest is None:
        return []
    try:
        table = agrochemical_lookup.get_table(deps.agrochem_table)
    except agrochemical_lookup.AgrochemTableError:
        logger.exception("agrochemical table is unusable; no label card for this scan")
        return []
    rows, _ = agrochemical_lookup.lookup(table, deps.denylist, crop=leading_crop, pest=pest)
    return [agrochemical_lookup.entry_from_row(r, table.table_version) for r in rows]


def _candidates(prediction: Prediction, label_map: LabelMap, leading_index: int) -> list[ScanCandidate]:
    out = []
    for ranked in prediction.top:
        lab = label_map.by_index(ranked.index)
        is_leading = ranked.index == leading_index
        out.append(
            ScanCandidate(
                label=lab.label,
                crop=lab.crop,
                condition=lab.condition,
                name_en=lab.name_en,
                name_hi=lab.name_hi,
                name_hi_status=lab.name_hi_status,
                probability=round(ranked.probability, 4),
                leading=is_leading,
                second_opinion_agrees=is_leading,  # a diagnosis exists only if the second model agreed with the leader
            )
        )
    # The agreed candidate first (it is the classifier's top choice by construction, but say so in the data).
    out.sort(key=lambda c: not c.leading)
    return out


async def diagnose(
    conn: asyncpg.Connection,
    farm_id,
    prepared: PreparedImage,
    deps: VisionDeps,
    *,
    language: str | None = None,
) -> DiagnosisRun:
    if language is not None and language not in TURN_B_LANGUAGE_RULES:
        raise ValueError(f"unsupported language {language!r}")

    report = quality.assess(prepared.rgb, deps.quality_thresholds)
    info = _quality_info(report)

    # Fail closed: an uncalibrated classifier's numbers mean nothing (app/vision/calibration.py).
    if deps.classifier is None or deps.calibration is None or deps.calibration.status != "calibrated":
        v = decision.Verdict("abstained", decision.VISION_NOT_CALIBRATED)
        return DiagnosisRun(_refusal(v, info, _versions(deps, vision_used=False)), verdict=v)

    verdict = decision.decide_quality(report)
    if verdict is not None:
        return DiagnosisRun(_refusal(verdict, info, _versions(deps, vision_used=False)), verdict=verdict)

    prediction = await run_in_threadpool(deps.classifier.predict, prepared.rgb)
    verdict = decision.decide_before_second_opinion(prediction, deps.label_map, deps.calibration)
    if verdict is not None:
        return DiagnosisRun(_refusal(verdict, info, _versions(deps, vision_used=False)), prediction=prediction, verdict=verdict)

    # The local checks passed: only now does the photo go to the vision provider.
    run: vlm.VlmRun | None = None
    try:
        run = await vlm.observe(deps.vision, prepared.jpeg, model=deps.vlm_model, label_map=deps.label_map)
    except vlm.VlmUnusable:
        logger.error("vision model gave no usable answer after %d attempts", vlm.MAX_ATTEMPTS)
    except Exception:  # noqa: BLE001 -- quota, network, authentication: the farmer gets an honest refusal, not a 500
        logger.exception("vision model call failed")

    observation = run.observation if run else None
    verdict = decision.decide_with_second_opinion(prediction, observation, deps.label_map, deps.calibration)
    base = DiagnosisRun(
        response=None,  # type: ignore[arg-type]  # filled below on every path
        prediction=prediction,
        observation=observation,
        vlm_usage=run.usage if run else None,
        vlm_attempts=run.attempts if run else vlm.MAX_ATTEMPTS,
        verdict=verdict,
    )
    versions = _versions(deps, vision_used=True)
    if verdict.outcome != "diagnosis":
        base.response = _refusal(verdict, info, versions)
        return base

    assert observation is not None and verdict.leading is not None and verdict.band is not None
    leading = verdict.leading
    farm_data = await farm_context.get_farm_context(conn, farm_id)
    # The farm record is evidence too: a photo that two models agree is another crop than the recorded one is not
    # diagnosed (before retrieval and the answer call, which would only spend tokens).
    mismatch = decision.decide_against_farm(leading, crop_scope.crops_named_in(farm_data.crop_name or ""))
    if mismatch is not None:
        base.verdict = mismatch
        base.response = _refusal(mismatch, info, versions, message=messages.crop_differs_refusal(farm_data.crop_name or ""))
        return base
    named_crops = frozenset({leading.crop})
    others = [deps.label_map.by_index(r.index) for r in prediction.top[1:]]
    symptoms = _guard_free_text(observation.visible_symptoms, deps)

    # Same grounding as /ask (ADR-0013/0014): retrieval is deterministic, scoped to the diagnosed crop.
    try:
        retrieval = await retrieve(
            conn,
            deps.embedder or get_query_embedder(),
            f"{leading.crop} {leading.name_en} symptoms and management",
            min_similarity=NO_SIMILARITY_GATE,
            top_k=settings.rag_context_chunks,
        )
    except asyncpg.PostgresError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError(f"Retrieval failed: {exc}") from exc
    scoped = crop_scope.scope_passages(retrieval.chunks, named_crops)
    passage_block, passages = build_passage_block(
        scoped, uncovered_crops=named_crops if not scoped else frozenset()
    )

    cards = _label_cards(leading.crop, leading.pest_for_label_lookup, deps) if not leading.is_healthy else []
    system = SCAN_TURN_B_PROMPT + (SCAN_LABEL_RULE if cards else "") + TURN_B_LANGUAGE_RULES.get(language or "", "")
    messages_b = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": scan_user_message(
                leading=leading, others=others, band_name=verdict.band.name, symptoms=symptoms, farm_data=farm_data
            ),
        },
        {"role": "user", "content": passage_block},
    ]

    base.answer_called = True
    try:
        scan_draft = await _draft_retrying(deps.llm, messages_b, model=deps.llm_model, schema=ScanDraft)
    except GenerationFailed:
        logger.error("no usable answer from the answer model for a diagnosed photo")
        failed = decision.Verdict("abstained", GENERATION_FAILED)
        base.verdict = failed
        base.response = _refusal(failed, info, versions, message=GENERATION_FAILED_MESSAGE)
        return base
    except Exception as exc:  # noqa: BLE001
        raise AgentError(f"Photo answer failed: {exc}") from exc

    advisory = finalize_advisory(
        scan_draft.to_draft(),
        farm_data=farm_data,
        live_data=None,
        passages=passages,
        named_crops=named_crops,
        question_text=f"Photo check of a {leading.crop} leaf: {leading.name_en}",
        denylist=deps.denylist,
        agrochemical_label=cards,
    )
    advisory = advisory.model_copy(update={"limitations": _scan_limitation(advisory)})

    if advisory.abstained:
        # The answer step refused (the model, the citation check, the banned-molecule or dose guard ...).
        # An abstention anywhere means no diagnosis is shown; the reason and the code-authored text are.
        reason = advisory.abstained_because or "model_abstained"
        refused = decision.Verdict("abstained", reason, leading=leading)
        # Every sentence of a refusal is code's: a model that abstained on its own may have left its own
        # words in `recommendation`, so those are not reused. The banned-molecule message is already code's.
        text = advisory.recommendation if reason == chemical_guard.BANNED_MOLECULE else abstain_message_for(reason)
        base.verdict = refused
        base.response = _refusal(refused, info, versions, message=text)
        return base

    cal = deps.calibration
    base.response = DiagnosisResponse(
        outcome="diagnosis",
        quality=info,
        candidates=_candidates(prediction, deps.label_map, leading.index),
        band=ConfidenceBand(
            name=verdict.band.name,
            observed_accuracy=verdict.band.observed_accuracy,
            n=verdict.band.n,
            measured_on=cal.calibrated_on,
        ),
        model_saw=ModelSaw(
            plant_part=observation.plant_part, crop=observation.crop, condition=observation.condition, symptoms=symptoms
        ),
        advisory=advisory,
        note=messages.DIAGNOSIS_NOTE,
        versions=versions,
    )
    return base


def _scan_limitation(advisory: AdvisoryResponse) -> str:
    """finalize_advisory's own note says an answer "rests only on your farm's record and weather", which is
    wrong for a photo answer. Replace it: when no document backs the advice, say that."""
    if advisory.abstained or advisory.retrieved_evidence:
        return ""
    return (
        "इस जवाब में किसी जाँचे हुए दस्तावेज़ का इस्तेमाल नहीं हुआ; यह सिर्फ़ फोटो की स्वचालित जाँच पर आधारित है। "
        "इलाज के लिए अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।\n\n"
        "No verified document was used for this answer; it rests only on the automatic photo check. "
        "For treatment, ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551)."
    )
