"""Quality gate: reject a photo that no classifier or model could read, before spending anything on it
(docs/ai/multimodal-vision.md pipeline step 1).

Five measurements, all plain numpy on a fixed-size grayscale or colour copy:

  * size            the shorter side in pixels (the classifier looks at a 224 px crop)
  * sharpness       variance of the Laplacian at a fixed 512 px scale (low = blurry)
  * exposure        mean brightness, and the share of near-black and near-white pixels
  * vegetation      the share of pixels that are leaf-coloured (green to yellow-green). It is a low
                    bar on purpose: a diseased leaf can be mostly brown, and a green object is NOT
                    called a plant by this check. It exists to say "there is no leaf in this photo at all"
                    (a wall, a face, the sky). Whether it IS a supported leaf is the classifier's job.

The thresholds are data (data/vision/quality-thresholds-v1.json), not constants in code, and the file
records how they were chosen. Until that file exists the built-in defaults below are used and are
reported as `thresholds_version: "builtin-default"`: initial guesses, replaced by the measurement in
evals/vision (false-reject rate on field photos, detection rate on degraded copies).

The gate never says a photo is good, only that it is not obviously unusable. A passed photo can still be
abstained on by every later step.
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

DEFAULT_PATH = Path(__file__).resolve().parents[4] / "data" / "vision" / "quality-thresholds-v1.json"

# Reason codes (the API maps each to a bilingual retake tip, app/vision/messages.py).
TOO_SMALL = "too_small"
TOO_BLURRY = "too_blurry"
TOO_DARK = "too_dark"
TOO_BRIGHT = "too_bright"
NO_VEGETATION = "no_vegetation"

_ANALYSIS_SIDE = 512  # long side of the working copy, so sharpness is comparable across photo sizes


@dataclass(frozen=True)
class QualityThresholds:
    version: str = "builtin-default"
    min_side_px: int = 224
    min_sharpness: float = 40.0  # variance of the Laplacian at 512 px; below this = too blurry
    min_mean_luma: float = 45.0  # 0..255; below this = too dark
    max_mean_luma: float = 215.0  # above this = too bright
    max_dark_fraction: float = 0.60  # share of pixels with luma < 25
    max_bright_fraction: float = 0.60  # share of pixels with luma > 240
    min_vegetation_fraction: float = 0.04


@dataclass(frozen=True)
class QualityMetrics:
    width: int
    height: int
    sharpness: float
    mean_luma: float
    dark_fraction: float
    bright_fraction: float
    vegetation_fraction: float


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    reasons: tuple[str, ...]  # every failed check, in a fixed order; [] when passed
    metrics: QualityMetrics
    thresholds_version: str

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "metrics": asdict(self.metrics),
            "thresholds_version": self.thresholds_version,
        }


def load_thresholds(path: Path | None = None) -> QualityThresholds:
    """The calibrated thresholds if the file exists, else the built-in defaults. A file that exists but
    is malformed raises: a silently different gate is worse than a loud one."""
    target = path or DEFAULT_PATH
    if not target.exists():
        return QualityThresholds()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return QualityThresholds(**data["thresholds"], version=data["version"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"quality thresholds {target} are unusable: {exc}") from exc


def _working_copy(rgb: np.ndarray) -> np.ndarray:
    """The photo scaled so its long side is _ANALYSIS_SIDE (never upscaled beyond that), as uint8 RGB."""
    h, w = rgb.shape[:2]
    scale = _ANALYSIS_SIDE / max(h, w)
    if scale >= 1.0:
        # Small photos are analysed at their own size: upscaling would invent smoothness.
        return rgb
    image = Image.fromarray(rgb).resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.BOX)
    return np.asarray(image, dtype=np.uint8)


def _luma(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32)
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def _laplacian_variance(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    c = gray[1:-1, 1:-1]
    lap = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4.0 * c
    return float(lap.var())


def vegetation_mask(rgb: np.ndarray) -> np.ndarray:
    """Leaf-coloured pixels: hue from yellow-green to green-cyan (40 to 170 degrees), enough saturation
    and brightness to have a colour at all. Computed without a colour-space library."""
    f = rgb.astype(np.float32) / 255.0
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    delta = mx - mn
    safe = np.where(delta == 0, 1.0, delta)
    hue = np.where(
        mx == r, ((g - b) / safe) % 6.0,
        np.where(mx == g, (b - r) / safe + 2.0, (r - g) / safe + 4.0),
    ) * 60.0
    saturation = np.where(mx == 0, 0.0, delta / np.where(mx == 0, 1.0, mx))
    return (delta > 0) & (hue >= 40.0) & (hue <= 170.0) & (saturation >= 0.15) & (mx >= 0.15)


def measure(rgb: np.ndarray) -> QualityMetrics:
    h, w = rgb.shape[:2]
    work = _working_copy(rgb)
    luma = _luma(work)
    return QualityMetrics(
        width=int(w),
        height=int(h),
        sharpness=_laplacian_variance(luma),
        mean_luma=float(luma.mean()),
        dark_fraction=float((luma < 25.0).mean()),
        bright_fraction=float((luma > 240.0).mean()),
        vegetation_fraction=float(vegetation_mask(work).mean()),
    )


def reasons_for(m: QualityMetrics, t: QualityThresholds) -> tuple[str, ...]:
    """The failed checks for a set of measurements, in a fixed order. Separate from `assess` so the
    evaluation (evals/vision) can apply thresholds to cached measurements without the pixels."""
    reasons: list[str] = []
    if min(m.width, m.height) < t.min_side_px:
        reasons.append(TOO_SMALL)
    if m.sharpness < t.min_sharpness:
        reasons.append(TOO_BLURRY)
    if m.mean_luma < t.min_mean_luma or m.dark_fraction > t.max_dark_fraction:
        reasons.append(TOO_DARK)
    if m.mean_luma > t.max_mean_luma or m.bright_fraction > t.max_bright_fraction:
        reasons.append(TOO_BRIGHT)
    if m.vegetation_fraction < t.min_vegetation_fraction:
        reasons.append(NO_VEGETATION)
    return tuple(reasons)


def assess(rgb: np.ndarray, thresholds: QualityThresholds | None = None) -> QualityReport:
    t = thresholds or load_thresholds()
    m = measure(rgb)
    reasons = reasons_for(m, t)
    return QualityReport(passed=not reasons, reasons=reasons, metrics=m, thresholds_version=t.version)
