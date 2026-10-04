"""Writes the API's OpenAPI document to apps/web/openapi.json (ADR-0017).

The web app's TypeScript types are generated from that file, so the browser and
the API cannot drift silently: tests/test_openapi_contract.py fails when the
committed file is stale.

    cd apps/api
    python scripts/dump_openapi.py            # rewrite the file
    cd ../web && npm run gen:types            # regenerate lib/api-types.ts
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

TARGET = Path(__file__).resolve().parents[2] / "web" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {TARGET}")
