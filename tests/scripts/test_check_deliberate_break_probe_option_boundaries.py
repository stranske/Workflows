"""Import probes must remove interactive flags without misreading option operands."""

import json
import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.fixture
def import_receipt(tmp_path, monkeypatch):
    """Prove the child imports our module and record its effective Python options."""
    monkeypatch.delenv("PYTHONWARNINGS", raising=False)
    receipt = tmp_path / "yaml.imported.json"
    (tmp_path / "yaml.py").write_text(
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "Path(__file__).with_suffix('.imported.json').write_text(\n"
        "    json.dumps({'interactive': sys.flags.interactive, 'warnoptions': sys.warnoptions}),\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    return receipt


def test_repeated_interactive_flags_leave_no_empty_probe_option(tmp_path, helper, import_receipt):
    command = (sys.executable, "-ii", "-m", "pytest", "tests/test_named.py::test_named")

    probe = helper["_pyyaml_probe_command"](command, tmp_path)

    assert probe == (sys.executable, "-c", helper["PYYAML_PROBE_CODE"])
    assert helper["_uses_pytest_runtime"](command) is True
    result = helper["_run"](probe, tmp_path)
    assert result.returncode == 0
    assert result.stdout == helper["PYYAML_PROBE_SENTINEL"] + "\n"
    assert result.stderr == ""
    assert json.loads(import_receipt.read_text(encoding="utf-8")) == {
        "interactive": 0,
        "warnoptions": [],
    }


def test_warning_operand_is_not_an_import_context_flag(tmp_path, helper, import_receipt):
    command = (
        sys.executable,
        "-W",
        "ignore::ImportWarning",
        "-m",
        "pytest",
        "tests/test_named.py::test_named",
    )
    probe = helper["_pyyaml_probe_command"](command, tmp_path)

    assert probe == (
        sys.executable,
        "-W",
        "ignore::ImportWarning",
        "-c",
        helper["PYYAML_PROBE_CODE"],
    )
    assert helper["_uses_pytest_runtime"](command) is True
    result = helper["_run"](probe, tmp_path)
    assert result.returncode == 0
    assert result.stdout == helper["PYYAML_PROBE_SENTINEL"] + "\n"
    assert result.stderr == ""
    assert json.loads(import_receipt.read_text(encoding="utf-8")) == {
        "interactive": 0,
        "warnoptions": ["ignore::ImportWarning"],
    }
