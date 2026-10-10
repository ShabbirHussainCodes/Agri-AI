"""The evaluation's label mapping and set names (evals/vision/vlabels.py, vdata.py): pure, no photos needed."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals" / "vision"))

import vlabels as V  # noqa: E402

LABELS = {lab["label"] for lab in json.loads((ROOT / "data" / "vision" / "label-map-v1.json").read_text(encoding="utf-8"))["labels"]}


def test_every_plantdoc_folder_maps_to_a_class_the_model_has():
    assert len(V.PLANTDOC_TO_CLASS) == 28
    assert set(V.PLANTDOC_TO_CLASS.values()) <= LABELS


def test_the_approximate_mappings_are_real_folders():
    assert V.APPROXIMATE <= set(V.PLANTDOC_TO_CLASS)


def test_two_plantdoc_folders_never_share_a_class_except_by_design():
    # PlantDoc has no folder for several PlantVillage classes (orange, squash is covered...), and each folder has its own class.
    values = list(V.PLANTDOC_TO_CLASS.values())
    assert len(values) == len(set(values))


def test_calibration_and_test_sets_are_disjoint_by_name():
    assert V.ID_CALIBRATION != V.ID_TEST
    assert set(V.OOD_CALIBRATION).isdisjoint(V.OOD_TEST)
    assert set(V.OOD_CALIBRATION) | set(V.OOD_TEST) == set(V.OOD_NAMES)
    assert all(n.endswith("_cal") for n in V.OOD_CALIBRATION) and all(n.endswith("_test") for n in V.OOD_TEST)
