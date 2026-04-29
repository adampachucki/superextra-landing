from __future__ import annotations

from evals.pairwise import _parse_response


def test_parse_response_uses_final_nested_json_object():
    text = """
The reports have several {non_json: braces} in prose.

```json
{"winner": "B", "dimensions": {"coverage": "B", "specificity": "TIE"}, "supporting_urls": ["https://example.com/a"]}
```
"""

    parsed = _parse_response(text)

    assert "parse_error" not in parsed
    assert parsed["winner"] == "B"
    assert parsed["dimensions"]["coverage"] == "B"
    assert parsed["supporting_urls"] == ["https://example.com/a"]


def test_parse_response_ignores_nested_winner_fields():
    text = """
```json
{"winner": "A", "dimensions": {"winner": "B", "coverage": "A"}, "supporting_urls": []}
```
"""

    parsed = _parse_response(text)

    assert parsed["winner"] == "A"
    assert parsed["dimensions"]["winner"] == "B"


def test_parse_response_rejects_invalid_winner():
    parsed = _parse_response('{"winner": "maybe", "supporting_urls": []}')

    assert parsed["winner"] is None
    assert parsed["parse_error"] == "invalid_winner:'maybe'"


def test_parse_response_reports_missing_json():
    parsed = _parse_response("No structured verdict here.")

    assert parsed["winner"] is None
    assert parsed["parse_error"] == "no_json"
