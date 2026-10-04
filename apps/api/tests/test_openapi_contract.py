"""The committed OpenAPI file (apps/web/openapi.json) matches the API (ADR-0017).
The web app's types are generated from it; a stale file means the browser is
built against a contract the API no longer has.

Compared by STRUCTURE (routes, methods, schema fields, required fields), not
byte for byte: another Python or Pydantic version words titles and defaults
slightly differently, and that must not fail the test."""
import json

from scripts import dump_openapi


def shape(doc: dict) -> dict:
    return {
        "routes": sorted(f"{method.upper()} {path}" for path, ops in doc["paths"].items() for method in ops),
        "schemas": {
            name: {"properties": sorted(s.get("properties", {})), "required": sorted(s.get("required", []))}
            for name, s in doc["components"]["schemas"].items()
        },
    }


def test_the_committed_openapi_document_has_the_same_contract_as_the_api():
    committed = json.loads(dump_openapi.TARGET.read_text(encoding="utf-8"))
    current = json.loads(dump_openapi.render())
    assert shape(committed) == shape(current), (
        "apps/web/openapi.json is stale. Run: cd apps/api && python scripts/dump_openapi.py "
        "&& cd ../web && npm run gen:types, and commit both files."
    )
