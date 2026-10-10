"""The pinned-model installer (app/vision/fetch_model.py): hash checks only, no download."""
import hashlib
import json

import pytest

from app.vision import fetch_model as fm


def manifest_for(data: bytes) -> dict:
    return {"repo": "o/r", "revision": "a" * 40, "file": "f.onnx", "sha256": hashlib.sha256(data).hexdigest()}


def test_a_file_with_the_manifests_hash_is_installed(tmp_path):
    src = tmp_path / "src.onnx"
    src.write_bytes(b"model bytes")
    dest = tmp_path / "models" / "vision" / "m.onnx"
    fm.install(src, manifest_for(b"model bytes"), dest)
    assert dest.read_bytes() == b"model bytes"


def test_a_file_with_any_other_hash_is_refused_and_nothing_is_written(tmp_path):
    src = tmp_path / "src.onnx"
    src.write_bytes(b"tampered")
    dest = tmp_path / "m.onnx"
    with pytest.raises(fm.ManifestError):
        fm.install(src, manifest_for(b"model bytes"), dest)
    assert not dest.exists()


@pytest.mark.parametrize("change", [{"repo": ""}, {"revision": None}, {"file": 3}, {"sha256": "abc"}])
def test_a_malformed_manifest_is_refused(tmp_path, change):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({**manifest_for(b"x"), **change}), encoding="utf-8")
    with pytest.raises(fm.ManifestError):
        fm.read_manifest(p)
    with pytest.raises(fm.ManifestError):
        fm.read_manifest(tmp_path / "missing.json")


def test_a_good_manifest_reads_back(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(manifest_for(b"x")), encoding="utf-8")
    assert fm.read_manifest(p)["repo"] == "o/r"


def test_the_build_time_destination_is_where_the_app_looks(monkeypatch):
    from app.vision import runtime

    monkeypatch.delenv("AGRIAI_VISION_MODEL_FILE", raising=False)
    monkeypatch.setattr(runtime.settings, "vision_model_file", None)
    monkeypatch.setenv("AGRIAI_EMBED_CACHE_DIR", str(runtime.settings.embed_cache_dir))
    assert fm.destination() == runtime.model_path()
    monkeypatch.setenv("AGRIAI_VISION_MODEL_FILE", "/x/y.onnx")
    assert str(fm.destination()) == "/x/y.onnx"
