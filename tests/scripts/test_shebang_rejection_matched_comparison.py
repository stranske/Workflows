"""Verify the current shebang-rejection matched baseline/candidate comparison."""

import json
import runpy
import tarfile
from pathlib import Path

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
