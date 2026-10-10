"""Builds the process-wide photo-check dependencies once (like app/retrieval/embedder.get_query_embedder).

A problem here must never stop the API from starting or /ask from working: a missing model file, a
calibration the model does not match, or an unreadable data file leaves `classifier` as None, and every
photo then gets the honest `vision_not_calibrated` refusal (app/vision/diagnose.py). The reason is logged.
"""
import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.providers.base import LLMProvider, VisionProvider
from app.safety import chemical_guard
from app.vision import calibration as calibration_mod
from app.vision import classifier as classifier_mod
from app.vision import labels, quality
from app.vision.fetch_model import MODEL_NAME as DEFAULT_MODEL_NAME  # one name, two readers
from app.vision.diagnose import VisionDeps

logger = logging.getLogger("agriai.vision")


def model_path() -> Path:
    return settings.vision_model_file or (settings.embed_cache_dir / "vision" / DEFAULT_MODEL_NAME)


@lru_cache(maxsize=1)
def _load_classifier_parts():
    """(label_map, calibration | None, classifier | None). Loaded once; restart after changing a file."""
    label_map = labels.get_label_map()
    try:
        calibration = calibration_mod.get_calibration()
    except calibration_mod.CalibrationError as exc:
        logger.error("photo check disabled: %s", exc)
        return label_map, None, None
    if calibration.status != "calibrated":
        logger.error("photo check disabled: calibration status is %r", calibration.status)
        return label_map, calibration, None
    path = model_path()
    if not path.exists():
        logger.error("photo check disabled: model file %s not found", path.name)
        return label_map, calibration, None
    try:
        return label_map, calibration, classifier_mod.load_classifier(path, label_map, calibration)
    except (classifier_mod.ModelMismatch, OSError, RuntimeError) as exc:
        logger.error("photo check disabled: %s", exc)
        return label_map, calibration, None


def build_deps(llm: LLMProvider, vision: VisionProvider) -> VisionDeps:
    label_map, calibration, classifier = _load_classifier_parts()
    return VisionDeps(
        classifier=classifier,
        calibration=calibration,
        label_map=label_map,
        vision=vision,
        llm=llm,
        vlm_model=settings.groq_vision_model,
        llm_model=settings.groq_chat_model,
        denylist=chemical_guard.get_denylist(),
        quality_thresholds=quality.load_thresholds(),
        agrochem_table=settings.agrochem_table,
    )


def photo_check_ready() -> bool:
    return _load_classifier_parts()[2] is not None


def label_map() -> labels.LabelMap:
    return labels.get_label_map()
