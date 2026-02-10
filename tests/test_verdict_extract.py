import json

from scripts.langchain import verdict_extract


def _build_summary(*rows: str) -> str:
    header = (
        "| Provider | Model | Verdict | Confidence | Summary |\n"
        "| --- | --- | --- | --- | --- |\n"
    )
    body = "\n".join(rows)
    return f"## Provider Summary\n\n{header}{body}\n"


def _parse_github_output(raw: str) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for line in raw.strip().splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        outputs[key] = value
    return outputs


def test_verdict_extract_emits_structured_github_outputs(tmp_path):
    summary = _build_summary(
        "| openai | gpt-5.2 | PASS | 0.92 | Looks good. |",
        "| anthropic | claude-sonnet-4-5 | CONCERNS | 0.84 | Missing edge case. |",
    )
    result = verdict_extract.build_verdict_result(summary, policy="worst")
    output_path = tmp_path / "github_output.txt"

    verdict_extract._write_github_outputs(result, str(output_path))

    outputs = _parse_github_output(output_path.read_text(encoding="utf-8"))

    assert outputs["verdict"] == "CONCERNS"
    assert outputs["needs_human"] == "true"
    assert outputs["policy"] == "worst"
    assert outputs["verdict_kind"] == "concerns"
    assert outputs["selected_provider"] == "anthropic"
    assert outputs["selected_model"] == "claude-sonnet-4-5"
    assert outputs["split_verdict"] == "true"
    assert outputs["needs_human_reason"]

    metadata = json.loads(outputs["verdict_metadata"])
    assert metadata["verdict"] == "CONCERNS"
    assert metadata["needs_human"] is True
