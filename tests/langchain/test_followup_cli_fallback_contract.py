"""Exercise the retained OSError fallback through CLI loading and inline guards."""

import json
import sys
from pathlib import Path

import pytest
from scripts.langchain import followup_issue_generator as generator


@pytest.mark.parametrize("error_stage", ["probe", "read"])
@pytest.mark.parametrize("failed_input", ["verification_comment", "original_issue", "codex_log"])
def test_main_isolates_file_errors_and_guards_literal_fallback(
    monkeypatch, tmp_path, capsys, failed_input, error_stage
):
    contents = {
        "verification_comment": "Verdict: PASS @100%\n### Concerns\n- Preserve file contents",
        "original_issue": "## Tasks\n- [ ] Preserve original task",
        "codex_log": "Optional execution context",
    }
    paths = {name: tmp_path / f"{name}.txt" for name in contents}
    for name, path in paths.items():
        path.write_text(contents[name])

    class InputPath:
        def __init__(self, value):
            self.path = Path(value)

        def is_file(self):
            if self.path == paths[failed_input] and error_stage == "probe":
                raise OSError("Cannot inspect input")
            return self.path.is_file()

        def read_text(self):
            if self.path == paths[failed_input]:
                assert error_stage == "read", "probe failure must stop before reading"
                raise OSError("Cannot read input")
            return self.path.read_text()

    scanned = []

    def check(text):
        scanned.append(text)
        return {"blocked": text == str(paths[failed_input]), "reason": "Review literal input"}

    generated = []

    def generate(**kwargs):
        generated.append(kwargs)
        return generator.FollowupIssue("Generated", "Generated body", ["follow-up"])

    argv = ["followup_issue_generator.py", "--pr-number", "123", "--no-llm", "--json"]
    for name, path in paths.items():
        argv.extend(["--" + name.replace("_", "-"), str(path)])
    monkeypatch.setattr(generator, "Path", InputPath)
    monkeypatch.setattr(generator, "check_prompt_injection", check)
    monkeypatch.setattr(generator, "generate_followup_issue", generate)
    monkeypatch.setattr(sys, "argv", argv)

    assert generator.main() == 0
    payload = json.loads(capsys.readouterr().out)
    if failed_input == "codex_log":
        assert scanned == [contents["verification_comment"], contents["original_issue"]]
        assert len(generated) == 1
        assert generated[0]["codex_log"] is None
        assert generated[0]["verification_data"].concerns == ["Preserve file contents"]
        assert generated[0]["original_issue"].tasks == ["Preserve original task"]
        assert payload == {
            "title": "Generated",
            "body": "Generated body",
            "labels": ["follow-up"],
        }
    else:
        expected = [str(paths[failed_input])]
        if failed_input == "original_issue":
            expected.insert(0, contents["verification_comment"])
        assert scanned == expected
        assert generated == []
        assert payload["guard_blocked"] is True
        assert payload["guard_reason"] == f"Review literal input (source: {failed_input})"
        assert "needs-human" in payload["labels"]
