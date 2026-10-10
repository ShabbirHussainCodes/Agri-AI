"""Loads the evaluation sets into rows (README.md "Data"). Files live in `_data/` (gitignored); nothing here
touches the network (that is vfetch.py).

A row is `Item(path, set, cls)`: `set` is one of the names in vlabels (plantdoc_train, rice_cal, ...) and `cls`
is the classifier class string for in-label-space photos, else None.
"""
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path

from vlabels import PLANTDOC_TO_CLASS

HERE = Path(__file__).resolve().parent
DATA = HERE / "_data"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SPLIT_SEED = 7


@dataclass(frozen=True)
class Item:
    path: Path
    set: str
    cls: str | None  # the classifier's class string, or None for an OOD photo
    source_class: str | None = None  # the data set's own class name (PlantDoc folder, rice disease ...)


def _images(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith("."))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def plantdoc_root() -> Path:
    """The folder that holds `train/` and `test/` (a GitHub archive nests it one level down)."""
    base = DATA / "plantdoc"
    for candidate in [base, *sorted(base.glob("*"))]:
        if (candidate / "train").is_dir() and (candidate / "test").is_dir():
            return candidate
    raise FileNotFoundError(f"PlantDoc is not in {base}; run vfetch.py first")


def plantdoc_items() -> tuple[list[Item], list[Item], dict]:
    """(train, test, info). Test photos whose bytes also appear in train are dropped from test and counted."""
    root = plantdoc_root()
    unknown = sorted({d.name for s in ("train", "test") for d in (root / s).iterdir() if d.is_dir()} - set(PLANTDOC_TO_CLASS))
    if unknown:
        raise ValueError(f"PlantDoc folders with no mapping: {unknown}")
    train, test = [], []
    for split, out in (("train", train), ("test", test)):
        for folder in sorted(d for d in (root / split).iterdir() if d.is_dir()):
            for path in _images(folder):
                out.append(Item(path, f"plantdoc_{split}", PLANTDOC_TO_CLASS[folder.name], folder.name))
    train_hashes = {file_sha256(i.path) for i in train}
    kept = [i for i in test if file_sha256(i.path) not in train_hashes]
    return train, kept, {"test_duplicates_removed": len(test) - len(kept), "train": len(train), "test": len(kept)}


def _split_half(items: list[Path], name_cal: str, name_test: str, classes: dict[Path, str | None]) -> list[Item]:
    """Seeded 50/50 split of a single-split data set into calibration and test (README: rice)."""
    shuffled = list(items)
    random.Random(SPLIT_SEED).shuffle(shuffled)
    half = len(shuffled) // 2
    return [Item(p, name_cal if i < half else name_test, None, classes.get(p)) for i, p in enumerate(shuffled)]


def rice_items() -> list[Item]:
    root = DATA / "rice"
    images = _images(root)
    return _split_half(images, "rice_cal", "rice_test", {p: p.parent.name for p in images})


def beans_items() -> list[Item]:
    root = DATA / "beans"
    out = []
    for split, name in (("validation", "beans_cal"), ("test", "beans_test")):
        out += [Item(p, name, None, p.parent.name) for p in _images(root / split)]
    return out


OBJECTS_PER_SPLIT = 400


def objects_items() -> list[Item]:
    """Imagenette has about 1,960 photos per split; 400 are drawn by a seeded shuffle so that this easy out-of-distribution
    set does not dominate the pooled false-accept rate next to rice (about 390) and beans (about 130). Decided on
    2026-10-10, before any photo had been classified (README.md, addendum A1)."""
    root = DATA / "imagenette"
    out = []
    for split, name in (("validation", "objects_cal"), ("test", "objects_test")):
        photos = _images(root / split)
        random.Random(SPLIT_SEED).shuffle(photos)
        out += [Item(p, name, None, p.parent.name) for p in sorted(photos[:OBJECTS_PER_SPLIT])]
    return out


def all_items() -> tuple[list[Item], dict]:
    train, test, info = plantdoc_items()
    return [*train, *test, *rice_items(), *beans_items(), *objects_items()], info
