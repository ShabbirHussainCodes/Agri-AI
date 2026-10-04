# AgriAI API image (ADR-0017). BUILD CONTEXT = the repository root:
#   docker build -f apps/api/Dockerfile -t agriai-api .
# The layout under /app mirrors the repo on purpose: the code finds data/ (crop table,
# denylist, label table) by walking up four directories from app/core/config.py.
#
# NOT built or run in the session that wrote it (no Docker there): treat the first build as
# a test, and read the log.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    AGRIAI_ENV=production \
    AGRIAI_EMBED_CACHE_DIR=/app/models \
    HF_HOME=/app/models

WORKDIR /app

COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install -r apps/api/requirements.txt

COPY apps/api/app apps/api/app
COPY data data

# Bake the ~470 MB embedding model into the image so a cold start does not download it. This
# is the same file and revision logic the app uses at runtime (app/retrieval/embedder.py).
RUN python - <<'PY'
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer
repo = "intfloat/multilingual-e5-small"
hf_hub_download(repo_id=repo, filename="onnx/model.onnx", cache_dir="/app/models")
AutoTokenizer.from_pretrained(repo, cache_dir="/app/models")
PY

# HF Spaces runs as user 1000 and expects port 7860 (the Space's README.md sets app_port).
RUN useradd -m -u 1000 user && chown -R user /app
USER user
WORKDIR /app/apps/api
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
