"""Downloads the model and the evaluation sets, pins what it got, and records SHA-256 hashes.

Run ONLY after the project owner has agreed to these downloads (CLAUDE.md section 5 and the phase brief): it
fetches about 1.25 GB from github.com and huggingface.co. All of it is public and none of it is farmer data; nothing
is uploaded anywhere. Every source is pinned to a commit so the result can be reproduced.

    python ../../evals/vision/vfetch.py model        # 24 MB int8 ONNX + config (CC-BY-SA-4.0)
    python ../../evals/vision/vfetch.py plantdoc     # ~1 GB zip from GitHub (CC-BY-4.0)
    python ../../evals/vision/vfetch.py rice beans imagenette   # HF parquet files -> image files (CC-BY-4.0, MIT, Apache-2.0)
    python ../../evals/vision/vfetch.py all

Downloaded archives are untrusted data: every archive member is checked to stay inside its target folder, and the
files are only ever opened by Pillow (never executed). Writes evals/vision/data_manifest.json (committed) and
data/vision/model-manifest.json (committed).
"""
import hashlib
import io
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(HERE))

import vdata  # noqa: E402

MANIFEST = HERE / "data_manifest.json"
MODEL_MANIFEST = ROOT / "data" / "vision" / "model-manifest.json"

MODEL_REPO = "rodynaemad/plant-disease-dinov2-small"
MODEL_FILE = "onnx/model_with_features_quantized.onnx"
GITHUB_REPO = "pratikkayal/PlantDoc-Dataset"

# (HF dataset repo, files to take, target folder under _data/, licence, split name each file becomes)
HF_SETS = {
    "rice": ("Project-AgML/rice_leaf_disease_classification_bd", [("data/train-00000-of-00001.parquet", "all")], "CC-BY-4.0"),
    "beans": ("AI-Lab-Makerere/beans", [("data/validation-00000-of-00001.parquet", "validation"), ("data/test-00000-of-00001.parquet", "test")], "MIT"),
    "imagenette": ("leandrodevai/imagenette-320px-resplit", [("320px/validation-00000-of-00001.parquet", "validation"), ("320px/test-00000-of-00001.parquet", "test")], "Apache-2.0"),
}


def sha256(path: Path) -> str:
    return vdata.file_sha256(path)


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}


def save_manifest(data: dict) -> None:
    MANIFEST.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def fetch_model() -> None:
    from huggingface_hub import HfApi, hf_hub_download

    from app.vision.runtime import model_path

    api = HfApi()
    revision = api.model_info(MODEL_REPO).sha
    onnx = Path(hf_hub_download(MODEL_REPO, MODEL_FILE, revision=revision))
    config = Path(hf_hub_download(MODEL_REPO, "config.json", revision=revision))
    dest = model_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(onnx, dest)
    id2label = json.loads(config.read_text(encoding="utf-8"))["id2label"]
    MODEL_MANIFEST.write_text(json.dumps({
        "repo": MODEL_REPO, "revision": revision, "file": MODEL_FILE, "sha256": sha256(dest), "size_bytes": dest.stat().st_size,
        "licence": "CC-BY-SA-4.0 (model); DINOv2 backbone Apache-2.0; trained on PlantVillage (CC-BY-SA)",
        "id2label": {k: id2label[k] for k in sorted(id2label, key=int)},
    }, indent=1) + "\n", encoding="utf-8")
    print(f"model {dest.name}: revision {revision[:12]}, sha256 {sha256(dest)[:16]}..., {dest.stat().st_size} bytes")


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> int:
    target = target.resolve()
    count = 0
    for member in archive.infolist():
        out = (target / member.filename).resolve()
        if target not in out.parents and out != target:
            raise ValueError(f"unsafe path in archive: {member.filename!r}")
        if member.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, out.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        count += 1
    return count


def fetch_plantdoc() -> None:
    api = json.loads(urllib.request.urlopen(f"https://api.github.com/repos/{GITHUB_REPO}/commits/master").read())
    commit = api["sha"]
    url = f"https://codeload.github.com/{GITHUB_REPO}/zip/{commit}"
    work = vdata.DATA / "_downloads"
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / f"plantdoc-{commit[:12]}.zip"
    print(f"downloading {url} ...", flush=True)
    with urllib.request.urlopen(url) as response, zip_path.open("wb") as out:
        shutil.copyfileobj(response, out, 1 << 20)
    target = vdata.DATA / "plantdoc"
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(zip_path) as archive:
        count = _safe_extract(archive, target)
    manifest = load_manifest()
    manifest["plantdoc"] = {"source": f"https://github.com/{GITHUB_REPO}", "commit": commit, "licence": "CC-BY-4.0",
                            "archive_sha256": sha256(zip_path), "archive_bytes": zip_path.stat().st_size, "files_extracted": count}
    save_manifest(manifest)
    print(f"plantdoc: {count} files, commit {commit[:12]}")


def _class_names(table) -> list[str] | None:
    meta = (table.schema.metadata or {}).get(b"huggingface")
    if not meta:
        return None
    features = json.loads(meta)["info"]["features"]
    return features.get("label", {}).get("names")


def fetch_hf_set(name: str) -> None:
    import pyarrow.parquet as pq
    from huggingface_hub import HfApi, hf_hub_download

    repo, files, licence = HF_SETS[name]
    revision = HfApi().dataset_info(repo).sha
    target = vdata.DATA / name
    if target.exists():
        shutil.rmtree(target)
    info = {"source": f"https://huggingface.co/datasets/{repo}", "revision": revision, "licence": licence, "files": {}}
    for filename, split in files:
        path = Path(hf_hub_download(repo, filename, repo_type="dataset", revision=revision))
        table = pq.read_table(path)
        names = _class_names(table)
        count = 0
        for i, row in enumerate(table.to_pylist()):
            image = row["image"]
            data = image["bytes"] if isinstance(image, dict) else image
            label = row.get("label")
            cls = names[label] if (names is not None and label is not None) else "unlabelled"
            folder = target / ("" if split == "all" else split) / cls
            folder.mkdir(parents=True, exist_ok=True)
            suffix = ".png" if data[:4] == b"\x89PNG" else ".jpg"
            (folder / f"{i:05d}{suffix}").write_bytes(data)
            count += 1
        info["files"][filename] = {"sha256": sha256(path), "bytes": path.stat().st_size, "images": count}
        print(f"{name}/{split}: {count} images")
    manifest = load_manifest()
    manifest[name] = info
    save_manifest(manifest)


def main() -> None:
    wanted = sys.argv[1:] or ["--help"]
    if wanted == ["--help"] or "-h" in wanted:
        print(__doc__)
        return
    if "all" in wanted:
        wanted = ["model", "plantdoc", "rice", "beans", "imagenette"]
    for item in wanted:
        if item == "model":
            fetch_model()
        elif item == "plantdoc":
            fetch_plantdoc()
        elif item in HF_SETS:
            fetch_hf_set(item)
        else:
            sys.exit(f"unknown target {item!r}")


if __name__ == "__main__":
    main()
