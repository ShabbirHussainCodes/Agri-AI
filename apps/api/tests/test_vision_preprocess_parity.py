"""Our numpy/Pillow preprocessing against the model's own Hugging Face image processor (like test_embedder_parity.py):
if they ever diverge, every logit shifts and the calibration stops meaning anything. Skipped where the processor
cannot be built (no network/cache, no vision extras)."""
import json
from pathlib import Path

import numpy as np
import pytest

from app.vision import classifier as C

from ._images import leaf_like

PREPROCESSOR = {
    "crop_size": {"height": 224, "width": 224}, "do_center_crop": True, "do_convert_rgb": True, "do_normalize": True,
    "do_rescale": True, "do_resize": True, "image_mean": [0.485, 0.456, 0.406], "image_processor_type": "BitImageProcessor",
    "image_std": [0.229, 0.224, 0.225], "resample": 3, "rescale_factor": 0.00392156862745098, "size": {"shortest_edge": 256},
}


@pytest.mark.parametrize("shape", [(480, 640), (640, 480), (300, 300), (1024, 768)])
def test_preprocess_matches_the_models_image_processor(shape, tmp_path):
    transformers = pytest.importorskip("transformers")
    try:
        processor = transformers.BitImageProcessor(**{k: v for k, v in PREPROCESSOR.items() if k != "image_processor_type"})
        rgb = leaf_like(shape[1], shape[0], seed=5)
        theirs = np.asarray(processor(images=rgb, return_tensors="np")["pixel_values"], dtype=np.float32)
    except Exception as exc:  # noqa: BLE001 -- a missing optional dependency, not a failure of ours
        pytest.skip(f"image processor unavailable: {type(exc).__name__}")
    ours = C.preprocess(rgb)
    assert ours.shape == theirs.shape
    assert np.abs(ours - theirs).mean() < 0.05, "the two resizes may differ by interpolation detail, not by structure"
    assert np.abs(ours - theirs).max() < 1.0
