"""Fetches the pinned classifier file and refuses anything but the exact bytes that were measured.

    python -m app.vision.fetch_model            # used by apps/api/Dockerfile at build time

data/vision/model-manifest.json (written by evals/vision/vfetch.py, committed) names the Hugging Face repo, the
exact commit, the file and its SHA-256. A file whose hash differs is deleted and the build fails: the calibration
(data/vision/calibration-v1.json) is only valid for these bytes, and app/vision/classifier.py checks the same hash
again at load. The ~24 MB file is not committed to Git (*.onnx is ignored); it is fetched, not trusted.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST = REPO_ROOT / "data" / "vision" / "model-manifest.json"
MODEL_NAME = "plant-disease-dinov2-small-int8.onnx"


def destination() -> Path:
    """Where the app looks for the file: the same rule as app.vision.runtime.model_path(), read from the environment
    directly because this runs at image build time, when the app's settings (database URL, keys) do not exist.
    A test keeps the two in step."""
    explicit = os.environ.get("AGRIAI_VISION_MODEL_FILE")
    if explicit:
        return Path(explicit)
    cache = Path(os.environ.get("AGRIAI_EMBED_CACHE_DIR") or REPO_ROOT / "ingest" / "_cache" / "models")
    return cache / "vision" / MODEL_NAME


class ManifestError(ValueError):
    pass


def read_manifest(path: Path = MANIFEST) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for key in ("repo", "revision", "file", "sha256"):
            if not isinstance(manifest.get(key), str) or not manifest[key]:
                raise ManifestError(f"manifest has no {key}")
        if len(manifest["sha256"]) != 64:
            raise ManifestError("manifest sha256 is not a SHA-256")
        return manifest
    except (OSError, ValueError) as exc:
        raise ManifestError(f"model manifest {path} is unusable: {exc}") from exc


def install(source: Path, manifest: dict, destination: Path) -> None:
    """Copy `source` to `destination` only if its hash is the manifest's; otherwise raise and leave nothing behind."""
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != manifest["sha256"]:
        raise ManifestError("downloaded model does not match the manifest's SHA-256")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def main() -> None:
    from huggingface_hub import hf_hub_download

    manifest = read_manifest()
    downloaded = Path(hf_hub_download(manifest["repo"], manifest["file"], revision=manifest["revision"]))
    target = destination()
    install(downloaded, manifest, target)
    print(f"vision model installed: {target.name} ({manifest['repo']} @ {manifest['revision'][:12]})")


if __name__ == "__main__":
    try:
        main()
    except ManifestError as exc:
        sys.exit(str(exc))
