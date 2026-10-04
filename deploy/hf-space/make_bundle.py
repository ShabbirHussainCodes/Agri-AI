"""Builds the folder to push to a Hugging Face Space.

A Space is its own git repository whose root must hold the Dockerfile, so this assembles
root = Dockerfile + apps/api/{app,requirements.txt} + data (no tests, no web app, no secrets).
Python only, so it runs the same on Windows, macOS and Linux.

    python deploy/hf-space/make_bundle.py /path/to/space-checkout
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)  # keep the Space equal to the repo; never touches the Space's .git
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    dest = Path(sys.argv[1]).resolve()
    (dest / "apps" / "api").mkdir(parents=True, exist_ok=True)
    copy_tree(ROOT / "apps" / "api" / "app", dest / "apps" / "api" / "app")
    copy_tree(ROOT / "data", dest / "data")
    shutil.copy(ROOT / "apps" / "api" / "requirements.txt", dest / "apps" / "api" / "requirements.txt")
    # The Dockerfile only uses paths relative to the build context, so it works unchanged at the root.
    shutil.copy(ROOT / "apps" / "api" / "Dockerfile", dest / "Dockerfile")
    shutil.copy(ROOT / ".dockerignore", dest / ".dockerignore")
    shutil.copy(HERE / "README.md", dest / "README.md")
    print(f"Bundle ready in {dest}. cd there, then: git add -A && git commit -m deploy && git push")


if __name__ == "__main__":
    main()
