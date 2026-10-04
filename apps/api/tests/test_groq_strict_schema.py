"""The schema sent to Groq in strict mode (app/providers/groq_provider.py).
Pure test: no network. Phase 5 added the first DraftAdvisory field with a
default, which Pydantic writes into the JSON schema as `"default"`."""
from app.providers.groq_provider import _make_strict
from app.schemas.advisory import DraftAdvisory


def _all_keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(node, list):
        for item in node:
            yield from _all_keys(item)


def test_pydantic_writes_a_default_for_irrigation_verdict():
    # If this ever stops being true the stripping below is moot, and this test says so.
    assert "default" in DraftAdvisory.model_json_schema()["properties"]["irrigation_verdict"]


def test_the_strict_schema_has_no_default_and_requires_every_field():
    schema = _make_strict(DraftAdvisory.model_json_schema())
    assert "default" not in set(_all_keys(schema))
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"]) >= {"irrigation_verdict", "evidence_basis"}
    assert schema["properties"]["irrigation_verdict"]["enum"] == ["irrigate_now", "wait", "cannot_assess", "not_applicable"]
