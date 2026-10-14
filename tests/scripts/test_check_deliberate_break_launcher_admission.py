"""Do not classify missing or opaque pytest launchers as the active Python runtime."""

import runpy
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.mark.parametrize("launcher", ["missing", "opaque"])
def test_unavailable_or_non_python_pytest_does_not_admit_active_runtime(
    tmp_path, monkeypatch, helper, launcher
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    candidate = bin_dir / "pytest"
    if launcher == "opaque":
        candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        candidate.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    # Use real PATH lookup and shebang parsing. An opaque launcher gives no
    # authority to repair PyYAML in this process's interpreter.
    assert helper["shutil"].which("pytest") == (str(candidate) if launcher == "opaque" else None)
    assert helper["_uses_pytest_runtime"](("pytest", "-q", "test_private.py")) is False
    assert candidate.exists() is (launcher == "opaque")
    if candidate.exists():
        assert candidate.read_text() == "#!/bin/sh\nexit 0\n"
