"""Shared builders for the vision tests: a calibration object, a fake classifier backend, a label map."""
import numpy as np

from app.vision.calibration import Band, Calibration, CropDecision, OodConfig
from app.vision.labels import get_label_map

LABELS = get_label_map()


def index_of(label: str) -> int:
    return next(lab.index for lab in LABELS.labels if lab.label == label)


TOMATO_EARLY = index_of("Tomato___Early_blight")
TOMATO_LATE = index_of("Tomato___Late_blight")
TOMATO_HEALTHY = index_of("Tomato___healthy")
POTATO_EARLY = index_of("Potato___Early_blight")
APPLE_SCAB = index_of("Apple___Apple_scab")
ORANGE_HLB = index_of("Orange___Haunglongbing_(Citrus_greening)")


def make_calibration(
    *,
    status: str = "calibrated",
    temperature: float = 1.0,
    ood_score: str = "max_logit",
    ood_threshold: float = 5.0,
    min_probability: float = 0.5,
    enabled_crops: tuple[str, ...] = ("tomato", "potato"),
    sha256: str = "0" * 64,
) -> Calibration:
    crops = {
        crop: CropDecision(enabled=crop in enabled_crops, n_calibration=40, selective_accuracy=0.85, reason="synthetic")
        for crop in ("tomato", "potato", "maize", "soybean", "citrus", "apple")
    }
    return Calibration(
        version="calibration-test",
        status=status,
        model={"repo": "test/model", "revision": "abc123def456abc123", "file": "m.onnx", "sha256": sha256},
        temperature=temperature,
        ood=OodConfig(score=ood_score, threshold=ood_threshold),
        min_probability=min_probability,
        bands=[
            Band(name="high", min_probability=0.9, observed_accuracy=0.93, n=100),
            Band(name="medium", min_probability=0.7, observed_accuracy=0.8, n=80),
            Band(name="low", min_probability=0.0, observed_accuracy=0.55, n=60),
        ],
        crops=crops,
        calibrated_on="synthetic test photos",
        generated_by="tests",
        date="2026-10-10",
        report="none",
    )


class FakeBackend:
    """Returns fixed logits (and optional features) whatever the photo is; records what it was given."""

    def __init__(self, logits: np.ndarray, features: np.ndarray | None = None):
        self._logits = np.asarray(logits, dtype=np.float32).reshape(1, -1)
        self._features = None if features is None else np.asarray(features, dtype=np.float32).reshape(1, -1)
        self.batches: list[np.ndarray] = []

    def run(self, batch: np.ndarray):
        self.batches.append(batch)
        return self._logits, self._features


def logits_for(index: int, *, top: float = 8.0, second: int | None = None, second_value: float = 2.0, n: int = 38) -> np.ndarray:
    """A logit vector that makes `index` the clear winner (and optionally `second` the runner-up)."""
    out = np.zeros(n, dtype=np.float32)
    out[index] = top
    if second is not None:
        out[second] = second_value
    return out
