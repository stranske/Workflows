import json

from scripts import debouncing_options_matrix


def test_render_markdown_includes_sections() -> None:
    content = debouncing_options_matrix.render_markdown(debouncing_options_matrix.OPTIONS)
    assert "# Advanced Debouncing Options" in content
    assert "## External Debouncer Service" in content
    assert "## GitHub App Filtering" in content
    assert "**Decision signals:**" in content
    assert "**Next steps:**" in content


def test_render_json_contains_expected_keys() -> None:
    content = debouncing_options_matrix.render_json(debouncing_options_matrix.OPTIONS)
    payload = json.loads(content)
    assert isinstance(payload, list)
    assert {
        "key",
        "title",
        "solves",
        "requirements",
        "risks",
        "decision_signals",
        "next_steps",
    } <= set(payload[0].keys())
