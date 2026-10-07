"""Reject runtime mutation receipts that do not prove the named test ran."""

import runpy
from pathlib import Path

import pytest


@pytest.fixture
def validate():
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / "docs/evidence/issue-3743/runtime-probes/replay.py"))[
        "validate_junit"
    ]


def report(
    *,
    name="probe[root]",
    classname="tests.scripts.private",
    failures=1,
    errors=0,
    skipped=0,
    outcome="<failure />",
):
    return (
        f'<testsuites><testsuite tests="1" failures="{failures}" errors="{errors}" '
        f'skipped="{skipped}"><testcase classname="{classname}" name="{name}">'
        f"{outcome}</testcase>"
        "</testsuite></testsuites>"
    )


def test_replay_accepts_only_executed_red_failure_and_green_pass(validate):
    node = "tests/scripts/private.py::probe[root]"
    assert validate(report(), node, "red") == {
        "tests": 1,
        "failures": 1,
        "errors": 0,
        "skipped": 0,
    }
    assert validate(report(failures=0, outcome=""), node, "green") == {
        "tests": 1,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }


def test_replay_rejects_errors_and_skips_even_with_failure_exit(validate):
    for invalid in (
        report(failures=0, errors=1, outcome="<error />"),
        report(failures=0, skipped=1, outcome="<skipped />"),
    ):
        with pytest.raises(RuntimeError):
            validate(invalid, "tests/scripts/private.py::probe[root]", "red")


def test_replay_rejects_wrong_case_and_inconsistent_outcome(validate):
    for invalid in (report(name="other[root]"), report(outcome="<error />")):
        with pytest.raises(RuntimeError):
            validate(invalid, "tests/scripts/private.py::probe[root]", "red")


def test_replay_rejects_same_named_case_from_another_module(validate):
    node = "tests/scripts/private.py::probe[root]"
    for phase in ("red", "green"):
        xml = report(
            classname="tests.scripts.other",
            failures=int(phase == "red"),
            outcome="<failure />" if phase == "red" else "",
        )
        with pytest.raises(RuntimeError):
            validate(xml, node, phase)


@pytest.mark.parametrize("fail_phase", [None, "red"])
def test_replay_main_copies_private_junit_and_restores_source(tmp_path, monkeypatch, fail_phase):
    import importlib.util
    import json
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    relative = Path("docs/evidence/issue-3743/runtime-probes/replay.py")
    spec = importlib.util.spec_from_file_location("runtime_replay", root / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    isolated = tmp_path / "checkout"
    monkeypatch.setattr(module, "__file__", str(isolated / relative))
    originals = {}
    for prefix in ("", "templates/consumer-repo/"):
        path = Path(prefix + "scripts/check_deliberate_break.py")
        target = isolated / path
        target.parent.mkdir(parents=True, exist_ok=True)
        originals[target] = (root / path).read_bytes()
        target.write_bytes(originals[target])
    test = isolated / "tests/scripts/test_check_deliberate_break_runtime_probes.py"
    test.parent.mkdir(parents=True)
    test.write_bytes((root / test.relative_to(isolated)).read_bytes())
    output = tmp_path / "output with spaces; literal $(data)"
    monkeypatch.setattr(sys, "argv", ["replay.py", "--output", str(output)])
    calls = []
    reports = []
    temporary_reports = []

    def run(argv, *, cwd, text, encoding, capture_output, timeout):
        phase = "red" if len(calls) % 2 == 0 else "green"
        assert cwd == isolated
        assert text and capture_output and encoding == "utf-8" and timeout == 60
        assert str(output) not in " ".join(argv)
        assert argv[:3] == [sys.executable, "-m", "pytest"]
        junit = Path(argv[-1].removeprefix("--junitxml="))
        assert junit.parent.name.startswith("runtime-probe-junit-")
        assert not junit.is_relative_to(output)
        node = argv[3]
        xml = report(
            name=node.rsplit("::", 1)[1],
            classname="tests.scripts.test_check_deliberate_break_runtime_probes",
            failures=int(phase == "red"),
            outcome="<failure />" if phase == "red" else "",
        )
        junit.write_text(xml, encoding="utf-8")
        calls.append(argv)
        reports.append(xml.encode())
        temporary_reports.append(junit)
        if fail_phase == phase:
            raise subprocess.TimeoutExpired(argv, timeout)
        return subprocess.CompletedProcess(argv, int(phase == "red"), "captured stdout", "")

    monkeypatch.setattr(module.subprocess, "run", run)
    if fail_phase:
        with pytest.raises(subprocess.TimeoutExpired):
            module.main()
    else:
        module.main()
        assert len(calls) == 28
        receipts = json.loads((output / "controls.json").read_text())
        assert len(receipts) == 14
        for i, xml in enumerate(reports):
            phase = "red" if i % 2 == 0 else "green"
            assert (output / f"{i // 2:02}-{phase}.xml").read_bytes() == xml
        assert all(r["source_sha256"] == r["restored_sha256"] for r in receipts)
    assert all(path.read_bytes() == original for path, original in originals.items())
    assert all(not path.exists() for path in temporary_reports)


@pytest.mark.parametrize("needs_formatting", [False, True])
def test_serial_black_returns_failure_for_unformatted_source(
    tmp_path, monkeypatch, needs_formatting
):
    root = Path(__file__).resolve().parents[2]
    main = runpy.run_path(
        str(root / "docs/evidence/issue-3743/runtime-probes/revalidation/black_serial.py")
    )["main"]
    (tmp_path / "pyproject.toml").write_text(
        '[tool.black]\ninclude = "[.]py$"\nextend-exclude = "^$"\ntarget-version = ["py312"]\n'
    )
    original = "x=1\n" if needs_formatting else "x = 1\n"
    source = tmp_path / "example.py"
    source.write_text(original)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == int(needs_formatting)
    assert source.read_text() == original
