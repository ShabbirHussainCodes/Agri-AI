"""The cached classifier output (vrun.py) as typed selectors. Pure numpy; no model, no files except the .npz."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Cache:
    key: np.ndarray
    set: np.ndarray
    cls: np.ndarray
    source: np.ndarray
    ok: np.ndarray
    logits: np.ndarray
    features: np.ndarray
    quality: np.ndarray  # columns: vrun.QUALITY_FIELDS
    latency_ms: np.ndarray
    model_sha256: str
    test_duplicates_removed: int
    degraded: dict[str, np.ndarray]  # kind -> quality rows

    def mask(self, name: str) -> np.ndarray:
        return (self.set == name) & self.ok

    def labels(self, mask: np.ndarray, class_index: dict[str, int]) -> np.ndarray:
        return np.array([class_index[c] for c in self.cls[mask]], dtype=np.int64)


QUALITY_COLUMNS = ("width", "height", "sharpness", "mean_luma", "dark_fraction", "bright_fraction", "vegetation_fraction")


def load(path: Path) -> Cache:
    z = np.load(path, allow_pickle=False)
    degraded: dict[str, np.ndarray] = {}
    if "degraded_set" in z.files:
        kinds, rows = z["degraded_kind"], z["degraded_quality"]
        degraded = {k: rows[kinds == k] for k in np.unique(kinds)}
    return Cache(
        key=z["key"], set=z["set"], cls=z["cls"], source=z["source"], ok=z["ok"], logits=z["logits"],
        features=z["features"], quality=z["quality"], latency_ms=z["latency_ms"],
        model_sha256=str(z["model_sha256"]), test_duplicates_removed=int(z["info_test_duplicates_removed"]),
        degraded=degraded,
    )


def col(rows: np.ndarray, name: str) -> np.ndarray:
    return rows[:, QUALITY_COLUMNS.index(name)]
