"""Runs the PRODUCTION image path and classifier once over every evaluation photo and caches the result.

For each photo: `prepare_image` (the same sanitising the API uses: decode, EXIF orientation, resize, JPEG
re-encode), the quality measurements, then the ONNX model's logits and features. Cached in `_runs/` as one .npz
so calibration and the report can be re-run in seconds, and so a change to the report never re-runs the model.
No network, no Groq quota. Also records per-photo latency (the classifier's CPU cost on this machine).

    python ../../evals/vision/vrun.py            # the model file comes from AGRIAI_VISION_MODEL_FILE or the default cache path
    python ../../evals/vision/vrun.py --degraded # also measure the quality gate on synthetic degradations of PlantDoc test
"""
import argparse
import io
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(HERE))

from app.vision import classifier as C  # noqa: E402
from app.vision import imaging, quality  # noqa: E402
from app.vision.runtime import model_path  # noqa: E402

import vdata  # noqa: E402

RUNS = HERE / "_runs"
CACHE = RUNS / "features.npz"
DEGRADATIONS = {
    "blur3": lambda im: im.filter(ImageFilter.GaussianBlur(3)),
    "blur6": lambda im: im.filter(ImageFilter.GaussianBlur(6)),
    "dark": lambda im: Image.fromarray(np.clip(np.asarray(im, dtype=np.float32) * 0.15, 0, 255).astype(np.uint8)),
    "washed": lambda im: Image.fromarray(np.clip(np.asarray(im, dtype=np.int32) + 170, 0, 255).astype(np.uint8)),
    "tiny": lambda im: im.resize((120, max(1, round(120 * im.height / im.width))), Image.Resampling.BILINEAR),
}
QUALITY_FIELDS = ("width", "height", "sharpness", "mean_luma", "dark_fraction", "bright_fraction", "vegetation_fraction")


def quality_row(rgb: np.ndarray) -> list[float]:
    m = quality.measure(rgb)
    return [float(getattr(m, f)) for f in QUALITY_FIELDS]


def run_items(items, backend, *, progress: int = 200) -> dict:
    rows = {"key": [], "set": [], "cls": [], "source": [], "ok": [], "logits": [], "features": [], "quality": [], "latency_ms": []}
    for n, item in enumerate(items, start=1):
        rows["key"].append(str(item.path.relative_to(vdata.DATA)))
        rows["set"].append(item.set)
        rows["cls"].append(item.cls or "")
        rows["source"].append(item.source_class or "")
        try:
            prepared = imaging.prepare_image(item.path.read_bytes())
        except imaging.ImageRejected:
            rows["ok"].append(False)
            rows["logits"].append(np.zeros(38, np.float32)); rows["features"].append(np.zeros(768, np.float32))
            rows["quality"].append([0.0] * len(QUALITY_FIELDS)); rows["latency_ms"].append(0.0)
            continue
        start = time.perf_counter()
        logits, features = backend.run(C.preprocess(prepared.rgb))
        rows["latency_ms"].append((time.perf_counter() - start) * 1000)
        rows["ok"].append(True)
        rows["logits"].append(logits.reshape(-1)); rows["features"].append(features.reshape(-1))
        rows["quality"].append(quality_row(prepared.rgb))
        if n % progress == 0:
            print(f"  {n}/{len(items)}", flush=True)
    return rows


def degraded_rows(test_items) -> dict:
    rows = {"key": [], "set": [], "kind": [], "quality": []}
    for item in test_items:
        try:
            prepared = imaging.prepare_image(item.path.read_bytes())
        except imaging.ImageRejected:
            continue
        base = Image.fromarray(prepared.rgb)
        for kind, fn in DEGRADATIONS.items():
            rgb = np.asarray(fn(base).convert("RGB"), dtype=np.uint8)
            rows["key"].append(str(item.path.relative_to(vdata.DATA))); rows["set"].append(f"degraded_{kind}")
            rows["kind"].append(kind); rows["quality"].append(quality_row(rgb))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--degraded", action="store_true")
    args = parser.parse_args()
    path = model_path()
    if not path.exists():
        sys.exit(f"model file not found: {path.name} (run vfetch.py)")
    items, info = vdata.all_items()
    print(f"{len(items)} photos; PlantDoc: {info}")
    backend = C.OnnxBackend(path)
    RUNS.mkdir(exist_ok=True)
    rows = run_items(items, backend)
    payload = {k: np.array(v) for k, v in rows.items()}
    payload["model_sha256"] = np.array(C.file_sha256(path))
    payload["info_test_duplicates_removed"] = np.array(info["test_duplicates_removed"])
    if args.degraded:
        _, test, _ = vdata.plantdoc_items()
        d = degraded_rows(test)
        for k, v in d.items():
            payload[f"degraded_{k}"] = np.array(v)
    np.savez_compressed(CACHE, **payload)
    ok = np.array(rows["ok"])
    print(f"wrote {CACHE.name}: {ok.sum()} decoded, {(~ok).sum()} unreadable; "
          f"latency p50 {np.percentile(np.array(rows['latency_ms'])[ok], 50):.0f} ms, p95 {np.percentile(np.array(rows['latency_ms'])[ok], 95):.0f} ms")


if __name__ == "__main__":
    main()
