"""Run the reusable Codex workflow's session-metrics step in a consumer checkout."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_analyze_session_outputs_in_consumer_checkout(tmp_path: Path) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/reusable-codex-run.yml").read_text())
    step = next(
        step for step in workflow["jobs"]["codex"]["steps"] if step.get("id") == "analyze_session"
    )
    shared = tmp_path / ".workflows-lib"
    (shared / "tools").mkdir(parents=True)
    shutil.copy(ROOT / "tools/codex_jsonl_parser.py", shared / "tools")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/__init__.py").write_text('raise AssertionError("loaded consumer tools")')

    output = tmp_path / "outputs"
    env = {
        **os.environ,
        "PATH": os.pathsep.join((str(Path(sys.executable).parent), os.environ["PATH"])),
        "PYTHONPATH": os.pathsep.join((str(shared), str(tmp_path))),
        "PR_NUM": "42",
        "GITHUB_OUTPUT": str(output),
    }
    session = tmp_path / "codex-session-42.jsonl"
    session.write_text(
        '{"type":"thread.started","thread_id":"t-1"}\n'
        '{"type":"item.completed","item_type":"assistant_message","content":"Done!"}\n'
    )
    subprocess.run(["bash", "-c", step["run"]], cwd=tmp_path, env=env, check=True, timeout=30)
    assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == {
        "session-available": "true",
        "event-count": "2",
        "message-count": "1",
        "command-count": "0",
        "file-change-count": "0",
        "todo-count": "0",
        "completed-todo-count": "0",
    }

    session.unlink()
    output.unlink()
    subprocess.run(["bash", "-c", step["run"]], cwd=tmp_path, env=env, check=True, timeout=30)
    assert output.read_text().splitlines() == ["session-available=false"]
