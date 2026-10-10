"""A small linear head over the frozen backbone's features, trained on FIELD photos (ADR-0018 addendum, protocol A2).

Why it exists: the backbone's published head was trained on lab photos and, measured on PlantDoc field photos, got 36.8 %
top-1 and could not tell a leaf it knows from rice, beans or a dog (evals/results/vision-*.md). The backbone's FEATURES
are good; this head is a replacement for the last linear layer, trained by evals/vision/vhead.py on PlantDoc-train photos
and stored as data (data/vision/head-v1.json, ~600 KB: a 27 x 768 weight matrix and 27 biases, standardisation folded in).

It maps the 768 features to logits in the SAME 38-class index space as the label map, so nothing downstream changes: a
class the head was not trained on gets a very low constant logit and can never win. The file names the SHA-256 of the
backbone it was trained on and the classifier refuses a head for a different backbone (app/vision/classifier.py).

FAIL-CLOSED like every other data file here: a malformed head raises, and a calibration that names a head the file does
not match means no photo is diagnosed.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path(__file__).resolve().parents[4] / "data" / "vision" / "head-v1.json"
UNTRAINED_LOGIT = -30.0  # a class with no training photo: far below any trained logit, so it never wins


class HeadError(ValueError):
    """The head file is malformed or is not for this backbone."""


class LinearHeadFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    backbone_sha256: str = Field(min_length=64, max_length=64)
    n_classes: int = Field(gt=0)  # size of the label map's index space (38)
    classes: list[int]  # the label-map indexes this head can name, ascending
    weight: list[list[float]]  # len(classes) x n_features, standardisation already folded in
    bias: list[float]
    l2: float
    n_head_train: int
    trained_on: str
    split_seed: int
    generated_by: str
    date: str

    @model_validator(mode="after")
    def _check(self) -> "LinearHeadFile":
        k = len(self.classes)
        if k == 0 or self.classes != sorted(set(self.classes)) or self.classes[0] < 0 or self.classes[-1] >= self.n_classes:
            raise ValueError("classes must be ascending, unique and inside the label space")
        if len(self.weight) != k or len(self.bias) != k:
            raise ValueError("weight and bias must have one row per class")
        widths = {len(row) for row in self.weight}
        if len(widths) != 1:
            raise ValueError("weight rows differ in length")
        return self


class LinearHead:
    def __init__(self, data: LinearHeadFile):
        self.meta = data
        self._w = np.asarray(data.weight, dtype=np.float64)
        self._b = np.asarray(data.bias, dtype=np.float64)
        self._classes = np.asarray(data.classes, dtype=np.int64)
        self.n_features = self._w.shape[1]
        self.n_classes = data.n_classes

    def logits(self, features: np.ndarray) -> np.ndarray:
        """(n_features,) or (1, n_features) -> (n_classes,) logits in the label-map index space."""
        f = np.asarray(features, dtype=np.float64).reshape(-1)
        if f.shape[0] != self.n_features:
            raise HeadError(f"expected {self.n_features} features, got {f.shape[0]}")
        out = np.full(self.n_classes, UNTRAINED_LOGIT, dtype=np.float64)
        out[self._classes] = self._w @ f + self._b
        return out.astype(np.float32)

    def logits_batch(self, features: np.ndarray) -> np.ndarray:
        f = np.asarray(features, dtype=np.float64)
        out = np.full((f.shape[0], self.n_classes), UNTRAINED_LOGIT, dtype=np.float64)
        out[:, self._classes] = f @ self._w.T + self._b
        return out.astype(np.float32)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_head(path: Path | None = None) -> LinearHead:
    target = path or DEFAULT_PATH
    try:
        return LinearHead(LinearHeadFile.model_validate(json.loads(target.read_text(encoding="utf-8"))))
    except (OSError, ValueError) as exc:
        raise HeadError(f"head {target} is unusable: {exc}") from exc


class HeadBackend:
    """A classifier Backend: the ONNX backbone's features, through this head. The backbone's own logits are ignored."""

    def __init__(self, backbone, head: LinearHead):
        self._backbone, self._head = backbone, head

    def run(self, batch: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        _, features = self._backbone.run(batch)
        if features is None:
            raise HeadError("the backbone returned no features")
        return self._head.logits(features)[None, :], features
