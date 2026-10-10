"""The ONNX leaf classifier and its out-of-distribution scores (docs/ai/multimodal-vision.md step 2).

Model: DINOv2-small with a linear head over the 38 PlantVillage classes (`rodynaemad/plant-disease-
dinov2-small`, int8 ONNX). It returns two outputs, `logits` (38) and `features` (768). It is a CLOSED-SET
model: it always names one of its 38 classes, even for a photo of a boot. Everything below exists to
measure how much to believe it, using numbers measured on field photos and stored in the calibration
file (app/vision/calibration.py), never the lab accuracy printed on the model card.

Pure numpy apart from the ONNX session, which is behind a tiny protocol so every test can run without the
~24 MB model file. The preprocessing is the model's own (resize the shorter side to 256 with bicubic,
centre crop 224, scale to 0..1, ImageNet mean and std).

Score convention: every OOD score is "HIGHER = MORE LIKE A SUPPORTED LEAF", so one comparison
(`score >= threshold`) serves all of them.
"""
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from app.vision.calibration import Calibration
from app.vision.labels import LabelMap

logger = logging.getLogger("agriai.vision")

RESIZE_SHORTEST = 256
CROP = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
TOP_K = 3


class ModelMismatch(RuntimeError):
    """The model file is not the one the calibration was measured for. Every probability and threshold
    would be meaningless, so the classifier refuses to run."""


class Backend(Protocol):
    def run(self, batch: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        """batch: float32 (1, 3, 224, 224). Returns (logits (1, n_classes), features (1, d) or None)."""
        ...


def preprocess(rgb: np.ndarray) -> np.ndarray:
    """uint8 RGB (H, W, 3) -> float32 (1, 3, 224, 224), the model's own preprocessing."""
    image = Image.fromarray(rgb)
    w, h = image.size
    scale = RESIZE_SHORTEST / min(w, h)
    new_w, new_h = max(CROP, round(w * scale)), max(CROP, round(h * scale))
    image = image.resize((new_w, new_h), Image.Resampling.BICUBIC)
    left, top = (new_w - CROP) // 2, (new_h - CROP) // 2
    image = image.crop((left, top, left + CROP, top + CROP))
    array = np.asarray(image, dtype=np.float32) / 255.0
    array = (array - MEAN) / STD
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None, ...], dtype=np.float32)


def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = logits.astype(np.float64) / temperature
    z = z - z.max()
    e = np.exp(z)
    return (e / e.sum()).astype(np.float64)


def logsumexp(logits: np.ndarray) -> float:
    z = logits.astype(np.float64)
    m = z.max()
    return float(m + np.log(np.exp(z - m).sum()))


def ood_scores(
    logits: np.ndarray, features: np.ndarray | None, temperature: float, centroids: np.ndarray | None
) -> dict[str, float]:
    """All the candidate scores for one photo. `feature_cosine` is present only with features AND
    centroids. Used both at run time (the one the calibration chose) and by the calibration script (all of
    them, to choose)."""
    scores = {
        "msp": float(softmax(logits, temperature).max()),
        "max_logit": float(logits.max()),
        "energy": logsumexp(logits),  # negative free energy: higher = more in-distribution
    }
    if features is not None and centroids is not None:
        f = features.astype(np.float64).reshape(-1)
        norm = np.linalg.norm(f)
        if norm > 0:
            scores["feature_cosine"] = float((centroids @ (f / norm)).max())
    return scores


@dataclass(frozen=True)
class Ranked:
    index: int
    probability: float  # temperature-scaled softmax
    logit: float


@dataclass(frozen=True)
class Prediction:
    top: tuple[Ranked, ...]  # best first, TOP_K long
    scores: dict[str, float]  # every OOD score available for this photo
    ood_score: float  # the one the calibration chose
    in_distribution: bool  # ood_score >= the calibrated threshold


class OnnxBackend:
    """onnxruntime on CPU. Imported lazily so that code that only needs the pure functions (the eval
    scripts' unit tests, the API's other routes) never loads it."""

    def __init__(self, model_path: Path, threads: int = 2):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name
        outputs = [o.name for o in self._session.get_outputs()]
        self._logits_name = "logits" if "logits" in outputs else outputs[0]
        self._features_name = "features" if "features" in outputs else None

    def run(self, batch: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        names = [self._logits_name] + ([self._features_name] if self._features_name else [])
        out = self._session.run(names, {self._input: batch})
        return np.asarray(out[0], dtype=np.float32), (np.asarray(out[1], dtype=np.float32) if len(out) > 1 else None)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Classifier:
    def __init__(self, backend: Backend, label_map: LabelMap, calibration: Calibration):
        self._backend = backend
        self._labels = label_map
        self._cal = calibration
        self._centroids = (
            np.asarray(calibration.ood.centroids, dtype=np.float64) if calibration.ood.centroids else None
        )

    def predict(self, rgb: np.ndarray) -> Prediction:
        logits, features = self._backend.run(preprocess(rgb))
        logits = logits.reshape(-1)
        if logits.shape[0] != len(self._labels.labels):
            raise ModelMismatch(f"model has {logits.shape[0]} classes, label map has {len(self._labels.labels)}")
        probs = softmax(logits, self._cal.temperature)
        order = np.argsort(-probs)[:TOP_K]
        scores = ood_scores(logits, features, self._cal.temperature, self._centroids)
        if self._cal.ood.score not in scores:
            raise ModelMismatch(f"OOD score {self._cal.ood.score!r} cannot be computed with this backend")
        chosen = scores[self._cal.ood.score]
        return Prediction(
            top=tuple(Ranked(int(i), float(probs[i]), float(logits[i])) for i in order),
            scores=scores,
            ood_score=chosen,
            in_distribution=chosen >= self._cal.ood.threshold,
        )


def load_classifier(model_path: Path, label_map: LabelMap, calibration: Calibration, head_path: Path | None = None) -> Classifier:
    """Builds the production classifier. Verifies the file is the exact one the calibration was measured
    for: a different quantisation or a re-exported model changes every score. If the calibration names a
    trained head (`model.head_sha256`), that head file is verified the same way and used; a calibration
    that names none uses the backbone's own head."""
    expected = calibration.model.get("sha256")
    if not expected:
        raise ModelMismatch("the calibration does not name the model's sha256")
    actual = file_sha256(model_path)
    if actual != expected:
        raise ModelMismatch("the model file is not the one the calibration was measured for")
    backend: Backend = OnnxBackend(model_path)
    head_hash = calibration.model.get("head_sha256")
    if head_hash:
        from app.vision import head as head_mod

        target = head_path or head_mod.DEFAULT_PATH
        try:
            if head_mod.file_sha256(target) != head_hash:
                raise ModelMismatch("the head file is not the one the calibration was measured for")
            head = head_mod.load_head(target)
        except (OSError, head_mod.HeadError) as exc:
            raise ModelMismatch(f"head unusable: {exc}") from exc
        if head.meta.backbone_sha256 != expected:
            raise ModelMismatch("the head was trained on a different backbone")
        if head.n_classes != len(label_map.labels):
            raise ModelMismatch("the head's class space is not the label map's")
        backend = head_mod.HeadBackend(backend, head)
    logger.info("vision classifier loaded (%s%s)", calibration.model.get("repo"), ", field head" if head_hash else "")
    return Classifier(backend, label_map, calibration)
