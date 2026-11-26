"""The reusable agent analysis step must preserve files in its caller's checkout."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"


@pytest.mark.parametrize("agent", ["claude", "codex", "cursor", "gemini", "muse"])
def test_pr_body_reaches_analysis_without_overwriting_checkout(agent, tmp_path):
    workflow = yaml.safe_load((WORKFLOWS / f"reusable-{agent}-run.yml").read_text())
    step = next(
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("id") == "llm_analysis"
    )
    shell = step["run"].replace("${{ steps.analyze_session.outputs.session-file }}", "session.txt")
    body = "- [ ] Handle quoted '$HOME'\n- [x] Keep the second line"
    receiver_file = tmp_path / "pr_body.md"
    receiver_file.write_bytes(b"existing receiver-owned data\n")
    auth = tmp_path / ".codex/auth.json"
    auth.parent.mkdir()
    auth.write_text("{}")
    analyzer = tmp_path / ".workflows-lib/scripts/analyze_codex_session.py"
    analyzer.parent.mkdir(parents=True)
    analyzer.write_text(
        "import sys\nfrom pathlib import Path\n"
        "body = Path(sys.argv[sys.argv.index('--pr-body-file') + 1]).read_bytes()\n"
        "Path('received').write_bytes(body)\nprint('{}')\n"
    )
    stubs = r"""
        gh() { printf "%s\n" "$TEST_BODY"; }
        codex() { return 1; }
        python3() { "$TEST_PYTHON" -S "$@"; }
    """
    output = tmp_path / "output"
    subprocess.run(
        ["bash", "-eo", "pipefail", "-c", stubs + shell],
        cwd=tmp_path,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "TEST_BODY": body,
            "PR_NUM": "42",
            "GITHUB_OUTPUT": str(output),
            "TEST_PYTHON": sys.executable,
        },
        check=True,
        capture_output=True,
        timeout=30,
    )
    assert "llm-analysis-run=true" in output.read_text().splitlines()
    assert (tmp_path / "received").read_bytes() == (
        body + ("\n" if agent == "codex" else "")
    ).encode()
    assert receiver_file.read_bytes() == b"existing receiver-owned data\n"
