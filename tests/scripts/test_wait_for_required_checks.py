"""wait_for_required_checks.sh: "no required checks reported" means not yet, not failed (Workflows#4133)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "wait_for_required_checks.sh"


def fake_gh(tmp_path: Path, missing_calls: int, final: str, final_rc: int) -> Path:
    """A gh that reports no required checks for the first `missing_calls` reads, then `final`."""
    counter = tmp_path / "calls"
    counter.write_text("0")
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'n=$(cat "{counter}"); n=$((n+1)); echo "$n" > "{counter}"\n'
        f'if [ "$n" -le {missing_calls} ]; then\n'
        "  echo \"no required checks reported on the 'harvest/auto' branch\"; exit 1\n"
        "fi\n"
        f"echo '{final}'; exit {final_rc}\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def run(tmp_path: Path, appear: int = 5) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(SCRIPT), "4133", str(appear), "5", "0"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_a_check_that_reports_late_is_waited_for(tmp_path: Path) -> None:
    fake_gh(tmp_path, missing_calls=3, final="summary\tpass\t35s", final_rc=0)
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "summary" in result.stdout


def test_a_failing_required_check_still_fails(tmp_path: Path) -> None:
    fake_gh(tmp_path, missing_calls=1, final="summary\tfail\t35s", final_rc=1)
    assert run(tmp_path).returncode == 1


def test_no_check_within_the_window_fails_with_the_reason(tmp_path: Path) -> None:
    fake_gh(tmp_path, missing_calls=10_000, final="", final_rc=0)
    result = run(tmp_path, appear=1)
    assert result.returncode == 1
    assert "no required check reported within 1s" in result.stdout
