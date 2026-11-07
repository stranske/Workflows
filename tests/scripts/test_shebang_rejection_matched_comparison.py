"""Verify the current shebang-rejection matched baseline/candidate comparison."""

import io
import json
import runpy
import shutil
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/shebang-rejection"
COMPARE = EVIDENCE / "compare_matched.py"
RECORDED = EVIDENCE / "replay-validation" / "proof.tar.gz"
OLD = ("tests.scripts.test_check_deliberate_break", "test_existing_helper_case")


def load_compare():
    return runpy.run_path(str(COMPARE))


def recorded_pytest_modules(name):
    with tarfile.open(RECORDED) as tar:
        command = json.loads(tar.extractfile(name).read())
    return [arg for arg in command["argv"] if arg.startswith("tests/")]


def coverage_report(executed, missing, executed_branches, missing_branches, excluded=None):
    excluded = list(excluded or [])
    statement_count = len(executed) + len(missing) + len(excluded)
    branch_count = len(executed_branches) + len(missing_branches)

    def one_file(lines):
        return {
            "executed_lines": list(lines),
            "missing_lines": list(missing),
            "excluded_lines": excluded,
            "executed_branches": [list(branch) for branch in executed_branches],
            "missing_branches": [list(branch) for branch in missing_branches],
            "summary": {
                "num_statements": statement_count,
                "num_branches": branch_count,
                "excluded_lines": len(excluded),
            },
        }

    return {
        "files": {
            "scripts/check_deliberate_break.py": one_file(executed),
            "templates/consumer-repo/scripts/check_deliberate_break.py": one_file(executed),
        },
        "totals": {
            "num_statements": statement_count * 2,
            "num_branches": branch_count * 2,
            "excluded_lines": len(excluded) * 2,
        },
    }


def passing_pair(module):
    expected = module["expected_added_nodes"](ROOT)
    baseline = {OLD: "passed"}
    candidate = dict(baseline)
    candidate.update({tuple(node): "passed" for node in expected})
    base = coverage_report([1], [2], [(3, 4)], [(3, 5)])
    candidate_cov = coverage_report([1, 2], [], [(3, 4), (3, 5)], [])
    comparison = module["build_comparison"](baseline, candidate, base, candidate_cov, expected)
    return comparison


def test_selection_matches_the_recorded_replay_validation_commands():
    module = load_compare()
    assert recorded_pytest_modules("baseline-command.json") == list(module["BASELINE_MODULES"])
    assert recorded_pytest_modules("candidate-command.json") == list(module["candidate_modules"]())
    assert module["candidate_modules"]()[-1] == module["SHEBANG"]
    assert module["candidate_modules"]()[:-1] == module["BASELINE_MODULES"]


def test_phase_commands_use_identical_coverage_and_pytest_settings():
    module = load_compare()
    baseline = module["phase_argv"](
        "python", module["BASELINE_MODULES"], Path("b.coverage"), Path("b.xml")
    )
    candidate = module["phase_argv"](
        "python", module["candidate_modules"](), Path("c.coverage"), Path("c.xml")
    )
    assert module["commands_match"](baseline, candidate) is True
    drifted = list(candidate)
    drifted[drifted.index("-q")] = "-vv"
    assert module["commands_match"](baseline, drifted) is False


@pytest.mark.parametrize(
    "defect, message",
    [
        ("interpreter", "phase settings"),
        ("coverage-config", "phase settings"),
        ("selection", "phase settings"),
        ("marker", "phase settings"),
        ("junit-output", "phase settings"),
        ("cwd", "cwd"),
        ("exit", "candidate exit"),
    ],
)
def test_retained_comparison_rejects_command_drift_before_reading_results(
    tmp_path, defect, message
):
    module = load_compare()
    directory = tmp_path / module["RUN"]
    directory.mkdir(parents=True)
    recorded = EVIDENCE / "matched-comparison"
    summary = json.loads((recorded / "summary.json").read_text())
    summary["cwd"] = str(tmp_path)
    (directory / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    commands = {
        phase: json.loads((recorded / f"{phase}-command.json").read_text())
        for phase in ("baseline", "candidate")
    }
    for command in commands.values():
        command["cwd"] = str(tmp_path)
    candidate = commands["candidate"]
    argv = candidate["argv"]
    if defect == "interpreter":
        argv[0] = "/different/python3"
    elif defect == "coverage-config":
        index = next(i for i, arg in enumerate(argv) if arg.startswith("--rcfile="))
        argv[index] = "--rcfile=different.ini"
    elif defect == "selection":
        argv.remove(module["BASELINE_MODULES"][0])
    elif defect == "marker":
        argv[argv.index("not slow")] = "not slow and not integration"
    elif defect == "junit-output":
        argv[-1] = commands["baseline"]["argv"][-1]
    elif defect == "cwd":
        candidate["cwd"] = str(tmp_path / "different")
    elif defect == "exit":
        candidate["exit"] = 1
    for phase, command in commands.items():
        (directory / f"{phase}-command.json").write_text(json.dumps(command), encoding="utf-8")
    # No JUnit or coverage results exist here: invalid commands must fail first.
    with pytest.raises(ValueError, match=message):
        module["validate_retained"](tmp_path)


@pytest.mark.parametrize("helper", ["scripts/", "templates/consumer-repo/scripts/"])
@pytest.mark.parametrize(
    "defect, message",
    [
        ("statement-universe", "statement/branch universes differ"),
        ("branch-universe", "statement/branch universes differ"),
        ("exclusion", "exclusions"),
        ("covered-line", "covered line or branch regression"),
        ("covered-branch", "covered line or branch regression"),
    ],
)
def test_raw_coverage_faults_are_detected_for_each_production_copy(helper, defect, message):
    module = load_compare()
    directory = EVIDENCE / "matched-comparison"
    baseline = json.loads((directory / "baseline.json").read_text())
    candidate = json.loads((directory / "candidate.json").read_text())
    path = helper + "check_deliberate_break.py"
    before = baseline["files"][path]
    after = candidate["files"][path]
    if defect == "statement-universe":
        after["missing_lines"][0] = 100_000
    elif defect == "branch-universe":
        after["missing_branches"][0] = [100_000, 100_001]
    elif defect == "exclusion":
        after["excluded_lines"].append(after["missing_lines"].pop())
        after["summary"]["excluded_lines"] += 1
    elif defect == "covered-line":
        line = before["executed_lines"][0]
        after["executed_lines"].remove(line)
        after["missing_lines"].append(line)
    elif defect == "covered-branch":
        branch = before["executed_branches"][0]
        after["executed_branches"].remove(branch)
        after["missing_branches"].append(branch)
    comparison = module["build_comparison"](
        module["junit_nodes"](directory / "baseline.xml"),
        module["junit_nodes"](directory / "candidate.xml"),
        baseline,
        candidate,
        module["expected_added_nodes"](ROOT),
    )
    assert any(message in error for error in module["contract_errors"](comparison))
    assert comparison["added_outcomes"] == ["passed"] * 8
    assert comparison["removed_nodes"] == []
    assert comparison["changed_old_outcomes"] == []
    if defect in {"covered-line", "covered-branch"}:
        assert comparison["universes_identical"] is True
    else:
        assert comparison["covered_line_regressions"] == []
        assert comparison["covered_branch_regressions"] == []


def test_template_coverage_path_does_not_replace_the_root_helper():
    module = load_compare()
    payload = coverage_report([1], [], [], [])
    payload["files"]["/tmp/work/scripts/check_deliberate_break.py"] = payload["files"][
        "scripts/check_deliberate_break.py"
    ]
    payload["files"]["/tmp/work/templates/consumer-repo/scripts/check_deliberate_break.py"] = (
        payload["files"]["templates/consumer-repo/scripts/check_deliberate_break.py"]
    )
    del payload["files"]["scripts/check_deliberate_break.py"]
    del payload["files"]["templates/consumer-repo/scripts/check_deliberate_break.py"]
    views = module["file_views"](payload)
    assert set(views) == set(module["HELPERS"])


def test_clean_comparison_adds_eight_passing_nodes_without_regressions():
    module = load_compare()
    comparison = passing_pair(module)
    assert module["contract_errors"](comparison) == []
    assert len(comparison["added_nodes"]) == 8
    assert comparison["removed_nodes"] == []
    assert comparison["changed_old_outcomes"] == []
    assert comparison["universes_identical"] is True
    assert comparison["exclusions"] == 0
    assert comparison["covered_line_regressions"] == []
    assert comparison["covered_branch_regressions"] == []
    assert comparison["deltas"]["scripts/check_deliberate_break.py"]["added_lines"] == [2]


def test_comparison_rejects_each_contract_breach():
    module = load_compare()
    clean = passing_pair(module)
    removed = json.loads(json.dumps(clean))
    removed["removed_nodes"] = [
        ["tests.scripts.test_check_deliberate_break", "test_existing_helper_case"]
    ]
    changed = json.loads(json.dumps(clean))
    changed["changed_old_outcomes"] = [
        [
            "tests.scripts.test_check_deliberate_break",
            "test_existing_helper_case",
            "passed",
            "failure",
        ]
    ]
    universe = json.loads(json.dumps(clean))
    universe["universes_identical"] = False
    excluded = json.loads(json.dumps(clean))
    excluded["exclusions"] = 2
    regression = json.loads(json.dumps(clean))
    regression["covered_line_regressions"] = [["scripts/check_deliberate_break.py", 1]]
    branch = json.loads(json.dumps(clean))
    branch["covered_branch_regressions"] = [["scripts/check_deliberate_break.py", [3, 4]]]
    failed_new = json.loads(json.dumps(clean))
    failed_new["added_outcomes"] = ["failure", *["passed"] * 7]
    extra = json.loads(json.dumps(clean))
    extra["added_nodes"] = [*clean["added_nodes"], ["tests.other", "test_extra"]]
    reports = (removed, changed, universe, excluded, regression, branch, failed_new, extra)
    assert all(module["contract_errors"](report) for report in reports)


def test_dtd_in_junit_is_rejected(tmp_path):
    module = load_compare()
    path = tmp_path / "junit.xml"
    path.write_text("<!DOCTYPE foo [<!ENTITY xxe 'x'>]><testsuites></testsuites>", encoding="utf-8")
    try:
        module["parse_junit"](path)
    except ValueError as exc:
        assert "DTD" in str(exc)
    else:
        raise AssertionError("DTD JUnit was accepted")


def test_retained_matched_comparison_meets_the_acceptance_contract():
    module = load_compare()
    summary = module["validate_retained"](ROOT)
    comparison = summary["comparison"]
    assert comparison["baseline_nodes"] == 340
    assert comparison["candidate_nodes"] == 348
    assert comparison["baseline_pass"] == 340
    assert comparison["candidate_pass"] == 348
    assert len(comparison["added_nodes"]) == 8
    assert comparison["added_outcomes"] == ["passed"] * 8
    assert comparison["removed_nodes"] == []
    assert comparison["changed_old_outcomes"] == []
    assert comparison["universes_identical"] is True
    assert comparison["exclusions"] == 0
    assert comparison["covered_line_regressions"] == []
    assert comparison["covered_branch_regressions"] == []
    for delta in comparison["deltas"].values():
        assert delta["removed_lines"] == []
        assert delta["removed_branches"] == []
    assert summary["historical_unchanged"] is True
    assert summary["interpreter"]["literal_anaconda_available"] is False
    assert summary["interpreter"]["path"]
    assert summary["commands"]["baseline"]["exit"] == 0
    assert summary["commands"]["candidate"]["exit"] == 0
    assert summary["archive"]["verified_manifest_members"] > 0


@pytest.mark.parametrize(
    "filename, message",
    [
        ("comparison.json", "stored comparison drifted"),
        ("summary.json", "summary comparison drifted"),
        ("input-bindings.json", "summary bindings drifted"),
        ("README.md", "archive verification failed"),
    ],
)
def test_retained_comparison_rejects_isolated_evidence_drift(tmp_path, filename, message):
    module = load_compare()
    directory = tmp_path / module["RUN"]
    shutil.copytree(EVIDENCE / "matched-comparison", directory)
    shutil.copyfile(EVIDENCE / "replay.py", tmp_path / module["REPLAY"])
    module["validate_retained"](tmp_path)
    path = directory / filename
    if filename == "README.md":
        path.write_text(path.read_text() + "Corrupted loose member.\n")
    else:
        payload = json.loads(path.read_text())
        if filename == "comparison.json":
            payload["candidate_pass"] -= 1
        elif filename == "summary.json":
            payload["comparison"]["candidate_pass"] -= 1
        else:
            payload[next(iter(payload))]["sha256"] = "0" * 64
        path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=message):
        module["validate_retained"](tmp_path)


@pytest.mark.parametrize("defect", [None, "missing-member", "member-hash", "loose-bytes"])
def test_pack_archive_roundtrip_and_isolated_member_rejection(tmp_path, defect):
    module = load_compare()
    payload = b"original receipt\n"
    (tmp_path / "receipt.txt").write_bytes(payload)
    (tmp_path / "summary.json").write_text("excluded summary")
    meta = module["pack_archive"](tmp_path)
    assert meta["verified_manifest_members"] == 1
    assert module["verify_archive"](tmp_path, meta)["verified"] is True
    archive = tmp_path / "proof.tar.gz"
    with tarfile.open(archive) as tar:
        assert set(tar.getnames()) == {"receipt.txt", "manifest.json"}
        members = {name: tar.extractfile(name).read() for name in tar.getnames()}
    if defect in {"missing-member", "member-hash"}:
        if defect == "missing-member":
            del members["receipt.txt"]
        else:
            members["receipt.txt"] = b"corrupt receipt!\n"
        with tarfile.open(archive, "w:gz") as tar:
            for name, data in members.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
        meta["sha256"] = module["digest"](archive.read_bytes())
        meta["bytes"] = archive.stat().st_size
    elif defect == "loose-bytes":
        (tmp_path / "receipt.txt").write_bytes(b"loose drift\n")
    report = module["verify_archive"](tmp_path, meta)
    assert report["sha256_matches_summary"] is True
    assert report["bytes_match_summary"] is True
    assert report["verified"] is (defect is None)
    if defect == "missing-member":
        assert report["manifest_covers_archive_files"] is False
    elif defect in {"member-hash", "loose-bytes"}:
        assert report["member_mismatches"] == ["receipt.txt"]


@pytest.mark.parametrize(
    "body, message",
    [
        (
            '<testsuites><testcase classname="m" name="n"/><testcase classname="m" name="n"/></testsuites>',
            "invalid JUnit node",
        ),
        ("<testsuites/>", "empty JUnit report"),
        ('<testsuites><testcase name="n"/></testsuites>', "invalid JUnit node"),
    ],
)
def test_duplicate_empty_and_unnamed_junit_are_rejected(tmp_path, body, message):
    module = load_compare()
    report = tmp_path / "junit.xml"
    report.write_text(body)
    with pytest.raises(ValueError, match=message):
        module["junit_nodes"](report)


def test_recorded_modules_separates_selection_from_settings():
    module = load_compare()
    modules, settings = module["recorded_modules"](
        ["python", "-m", "pytest", "tests/first.py", "tests/second.py", "-q", "-o", "addopts="]
    )
    assert modules == ["tests/first.py", "tests/second.py"]
    assert settings == ["-q", "-o", "addopts="]
