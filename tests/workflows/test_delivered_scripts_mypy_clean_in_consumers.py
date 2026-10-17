"""Scripts delivered to consumers must type-check in a consumer layout (Workflows#3993).

trip-planner's mypy gate rejected the delivered scripts/ledger_validate.py: its direct-execution
import fallbacks (`belt_ledger_completion`, `utils.paths`) cannot be resolved there. A consumer
has none of this repo's `src/` or mypy settings, so check the files alone with only a package
marker next to them.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DELIVERED = ("scripts/ledger_validate.py", "scripts/belt_ledger_completion.py")

mypy_available = (
    subprocess.run([sys.executable, "-m", "mypy", "--version"], capture_output=True).returncode == 0
)


@pytest.mark.skipif(not mypy_available, reason="mypy is not installed")
def test_delivered_ledger_scripts_type_check_in_a_consumer_layout(tmp_path):
    package = tmp_path / "scripts"
    package.mkdir()
    (package / "__init__.py").write_text("")
    for rel in DELIVERED:
        shutil.copy(ROOT / rel, package / Path(rel).name)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "scripts", "--warn-unused-ignores", "--no-incremental"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout
    assert "Success: no issues found in 3 source files" in result.stdout
