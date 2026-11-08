"""Exercise the measurement refusal boundary and real two-arm pytest execution."""

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from scripts import measure_verifier_runtime as measure


def fixture_repo(tmp_path, monkeypatch, *, change_source=False, object_format="sha1"):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", f"--object-format={object_format}", str(repo)], check=True)
    for key, value in [("user.name", "Measurement Test"), ("user.email", "test@example.invalid")]:
        subprocess.run(["git", "-C", str(repo), "config", key, value], check=True)
    (repo / "scripts/langchain").mkdir(parents=True)
    (repo / measure.VERIFIER).write_text(
        "def decision(value):\n    if value:\n        return True\n    return False\n"
    )
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\n[tool.coverage.run]\nbranch=true\nsource=["scripts"]\n'
    )
    (repo / "requirements.lock").write_text("# same common environment\n")
    workflow = repo / ".github/workflows/maint-88-verifier-runtime-comparison.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: fixture\n")
    for name in measure.SUITES:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from scripts.langchain.pr_verifier import decision\n"
            "def test_decision():\n    assert decision(True)\n    assert not decision(False)\n"
        )

    def commit(message):
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)
        return measure.git(repo, "rev-parse", "HEAD").decode().strip()

    baseline = commit("baseline")
    (repo / measure.SUITES[0]).write_text(
        (repo / measure.SUITES[0]).read_text() + "\n# candidate\n"
    )
    if change_source:
        (repo / measure.VERIFIER).write_text("def decision(value):\n    return not value\n")
    candidate = commit("candidate")
    monkeypatch.setattr(measure, "BASELINE", baseline)
    monkeypatch.setattr(measure, "CANDIDATE", candidate)
    return repo


def test_prepare_refuses_changed_production_and_reused_output(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch, change_source=True)
    with pytest.raises(ValueError, match="Production verifier bytes differ"):
        measure.prepare(repo, tmp_path / "out")
    with pytest.raises(FileExistsError):
        measure.prepare(repo, tmp_path / "out")


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_prepare_cli_selects_explicit_immutable_source_pair(tmp_path, monkeypatch, object_format):
    repo = fixture_repo(tmp_path, monkeypatch, object_format=object_format)
    output = tmp_path / "selected"
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(measure.__file__).resolve()),
            "prepare",
            "--output",
            str(output),
            "--baseline",
            measure.BASELINE,
            "--candidate",
            measure.CANDIDATE,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((output / "manifest.json").read_text())
    for name, ref in (("baseline", measure.BASELINE), ("candidate", measure.CANDIDATE)):
        assert manifest["arms"][name]["commit"] == ref
        assert (
            manifest["arms"][name]["tree"]
            == measure.git(repo, "rev-parse", f"{ref}^{{tree}}").decode().strip()
        )
        assert manifest["arms"][name]["sha256"][measure.SUITES[0]] == measure.sha(
            output / name / measure.SUITES[0]
        )
    assert manifest["dependency_lock"] == "candidate/requirements.lock"


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("ref", ["", "main", "HEAD", "a" * 39, "a" * 41, "A" * 40, "--all"])
def test_prepare_refuses_mutable_or_malformed_refs_before_git(tmp_path, monkeypatch, arm, ref):
    refs = {"baseline": "a" * 40, "candidate": "b" * 40}
    refs[arm] = ref

    def unexpected_git(*args):
        pytest.fail("Invalid source selection must be rejected before Git is called")

    monkeypatch.setattr(measure, "git", unexpected_git)
    with pytest.raises(ValueError, match="full lowercase.*commit"):
        measure.prepare(tmp_path, tmp_path / "out", **refs)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("object_kind", ["tree", "blob", "tag"])
def test_prepare_requires_commit_objects(tmp_path, monkeypatch, arm, object_kind):
    repo = fixture_repo(tmp_path, monkeypatch)
    refs = {"baseline": measure.BASELINE, "candidate": measure.CANDIDATE}
    if object_kind == "tag":
        subprocess.run(["git", "-C", str(repo), "tag", "-am", "fixture", "source"], check=True)
    spec = {"tree": "HEAD^{tree}", "blob": "HEAD:requirements.lock", "tag": "refs/tags/source"}[
        object_kind
    ]
    refs[arm] = measure.git(repo, "rev-parse", spec).decode().strip()
    with pytest.raises(ValueError, match="Source object must be a commit"):
        measure.prepare(repo, tmp_path / "out", **refs)
    assert not (tmp_path / "out").exists()


def test_explicit_source_pair_preserves_production_identity_check(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch, change_source=True)
    with pytest.raises(ValueError, match="Production verifier bytes differ"):
        measure.prepare(
            repo, tmp_path / "out", baseline=measure.BASELINE, candidate=measure.CANDIDATE
        )


@pytest.mark.parametrize("section", ["coverage", "pytest"])
def test_explicit_source_pair_preserves_configuration_checks(tmp_path, monkeypatch, section):
    repo = fixture_repo(tmp_path, monkeypatch)
    config = repo / "pyproject.toml"
    text = config.read_text()
    if section == "coverage":
        text = text.replace("branch=true", "branch=false")
    else:
        text = text.replace("[tool.pytest.ini_options]", '[tool.pytest.ini_options]\naddopts="-q"')
    config.write_text(text)
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "changed config"], check=True)
    candidate = measure.git(repo, "rev-parse", "HEAD").decode().strip()
    with pytest.raises(ValueError, match=section + " configurations differ"):
        measure.prepare(repo, tmp_path / "out", baseline=measure.BASELINE, candidate=candidate)


@pytest.mark.parametrize(
    "mode,flags",
    [
        ("run", ["--baseline", "a" * 40, "--candidate", "b" * 40]),
        ("prepare", ["--candidate", "a" * 40]),
    ],
)
def test_cli_refuses_inapplicable_or_partial_source_selection(tmp_path, mode, flags):
    output = tmp_path / "out"
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(measure.__file__).resolve()),
            mode,
            "--output",
            str(output),
            *flags,
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "source selection requires prepare and both --baseline and --candidate" in proc.stderr
    assert not output.exists()


def test_real_arms_keep_one_environment_and_preserve_coverage(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)
    assert measure.run(output) == 0
    result = json.loads((output / "result.json").read_text())
    assert result["packages_unchanged"]
    assert result["outcome_comparison"] == {"successful": True, "gaps": []}
    assert result["timing_comparison"] == {"available": True, "gaps": []}
    assert result["arms"]["baseline"]["command"] == result["arms"]["candidate"]["command"]
    assert result["verifier_coverage"]["baseline_lines"] > 0
    assert result["verifier_coverage"]["candidate_branches"] > 0
    assert not result["verifier_coverage"]["lost_lines"]
    assert len(result["artifact_sha256"]) == 18
    assert all(row["phases"]["available"] for row in result["arms"].values())
    assert (
        result["phase_plugin_sha256"]
        == measure.hashlib.sha256(measure.PHASE_PLUGIN.encode()).hexdigest()
    )
    assert result["source_integrity"]["verified"] is True
    for phase in ("before", "after"):
        receipt = result["source_integrity"][phase]
        assert receipt["verified"] is True
        assert receipt["gaps"] == []
        for arm in ("baseline", "candidate"):
            assert receipt["sha256"][arm] == result["manifest"]["arms"][arm]["sha256"]


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize(
    "path", [*measure.SUITES, measure.VERIFIER, "pyproject.toml", "requirements.lock"]
)
def test_run_refuses_source_drift_before_executing_either_arm(tmp_path, monkeypatch, arm, path):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)
    source = output / arm / path
    source.write_bytes(source.read_bytes() + b"\n# changed after preparation\n")

    def unexpected(*args, **kwargs):
        pytest.fail("Changed source must be refused before package inspection or pytest execution")

    monkeypatch.setattr(measure, "packages", unexpected)
    monkeypatch.setattr(measure.subprocess, "run", unexpected)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["arms"] == {}
    assert result["source_integrity"]["verified"] is False
    assert any(arm in gap and path in gap for gap in result["source_integrity"]["before"]["gaps"])
    assert result["verifier_coverage"] is None
    assert result["outcome_comparison"]["successful"] is False
    assert result["timing_comparison"]["available"] is False


@pytest.mark.parametrize("defect", ["missing-file", "missing-hash", "missing-arm"])
def test_run_refuses_incomplete_source_identity_with_a_receipt(tmp_path, monkeypatch, defect):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if defect == "missing-file":
        (output / "candidate" / measure.VERIFIER).unlink()
    elif defect == "missing-hash":
        del manifest["arms"]["candidate"]["sha256"][measure.VERIFIER]
    else:
        del manifest["arms"]["candidate"]
    manifest_path.write_text(json.dumps(manifest))

    def unexpected(*args, **kwargs):
        pytest.fail("Incomplete source identity must be refused before execution")

    monkeypatch.setattr(measure, "packages", unexpected)
    monkeypatch.setattr(measure.subprocess, "run", unexpected)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["source_integrity"]["verified"] is False
    assert result["source_integrity"]["before"]["gaps"]
    assert result["arms"] == {}


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_run_withholds_comparison_when_source_changes_during_execution(tmp_path, monkeypatch, arm):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)

    def fake_pytest(command, *, cwd, **kwargs):
        _junit_receipt(cwd, name="pytest-junit.xml")
        coverage = {
            "meta": {"branch_coverage": True},
            "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}},
        }
        (cwd / "coverage.json").write_text(json.dumps(coverage))
        # Change the other arm too: both snapshots must be checked at the end,
        # regardless of which arm ran first on this interpreter.
        if cwd.name == "baseline":
            source = output / arm / measure.VERIFIER
            source.write_bytes(source.read_bytes() + b"\n# changed during execution\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(measure, "packages", lambda: [])
    monkeypatch.setattr(measure.platform, "platform", lambda: "fixture-platform")
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["source_integrity"]["before"]["verified"] is True
    assert result["source_integrity"]["after"]["verified"] is False
    assert result["source_integrity"]["verified"] is False
    assert any(arm in gap for gap in result["source_integrity"]["after"]["gaps"])
    assert result["outcome_comparison"]["successful"] is True
    assert result["timing_comparison"]["available"] is True
    assert result["verifier_coverage"] is None
    assert "source integrity" in result["coverage_error"]
    assert len(result["artifact_sha256"]) == 6


def test_coverage_loss_is_not_reported_as_equivalence():
    before = {
        "meta": {"branch_coverage": True},
        "files": {
            measure.VERIFIER: {"executed_lines": [1, 2], "executed_branches": [[1, 2], [1, 3]]}
        },
    }
    after = {
        "meta": {"branch_coverage": True},
        "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, 2]]}},
    }
    result = measure.coverage_comparison(before, after)
    assert result["lost_lines"] == [2]
    assert result["lost_branches"] == [(1, 3)]


def test_fresh_graph_requires_explicit_candidate_fetch(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    subprocess.run(["git", "init", "-q", str(fresh)], check=True)
    subprocess.run(
        ["git", "-C", str(fresh), "fetch", "--quiet", str(repo), measure.BASELINE], check=True
    )
    subprocess.run(
        ["git", "-C", str(fresh), "checkout", "--quiet", "--detach", "FETCH_HEAD"], check=True
    )
    with pytest.raises(subprocess.CalledProcessError):
        measure.git(fresh, "archive", measure.CANDIDATE)
    # The workflow's retained-PR-head fetch supplies this exact object. A normal
    # branch-history fetch did not: the pre-squash head is a separate graph tip.
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/pull/3950/head", measure.CANDIDATE], check=True
    )
    subprocess.run(
        ["git", "-C", str(fresh), "fetch", "--quiet", str(repo), "refs/pull/3950/head"], check=True
    )
    assert measure.git(fresh, "rev-parse", "FETCH_HEAD").decode().strip() == measure.CANDIDATE
    output = tmp_path / "fresh-output"
    measure.prepare(fresh, output)
    assert (
        json.loads((output / "manifest.json").read_text())["arms"]["candidate"]["commit"]
        == measure.CANDIDATE
    )


def test_source_archive_cannot_escape_its_arm(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        member = tarfile.TarInfo("../../escaped-source")
        member.size = 4
        tar.addfile(member, io.BytesIO(b"oops"))
    real_git = measure.git
    monkeypatch.setattr(
        measure,
        "git",
        lambda repo, *args: archive.getvalue() if args[0] == "archive" else real_git(repo, *args),
    )
    with pytest.raises(ValueError, match="escapes"):
        measure.prepare(repo, tmp_path / "out")
    assert not (tmp_path / "escaped-source").exists()


def test_prepare_entry_point_needs_no_installed_packages():
    # Preparation runs before pip install on a fresh setup-python interpreter.
    result = subprocess.run(
        [sys.executable, "-S", str(Path(measure.__file__).resolve()), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "prepare" in result.stdout


def test_source_archive_refuses_links(tmp_path):
    target = tmp_path / "arm"
    target.mkdir()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../escaped-source"
        tar.addfile(member)
    with pytest.raises(ValueError, match="links and special"):
        measure.extract_source(archive.getvalue(), target)
    assert not (target / "link").exists()


@pytest.mark.parametrize(
    "entry",
    [
        None,
        {},
        {"executed_lines": [1]},
        {"executed_lines": None, "executed_branches": []},
        {"executed_lines": [True], "executed_branches": []},
        {"executed_lines": [0], "executed_branches": []},
        {"executed_lines": [-1], "executed_branches": []},
        {"executed_lines": ["1"], "executed_branches": []},
        {"executed_lines": [], "executed_branches": None},
        {"executed_lines": [], "executed_branches": [[1]]},
        {"executed_lines": [], "executed_branches": [[1, 2, 3]]},
        {"executed_lines": [], "executed_branches": [[True, 2]]},
        {"executed_lines": [], "executed_branches": [[1, 0]]},
        {"executed_lines": [], "executed_branches": [[1, "2"]]},
    ],
)
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_coverage_comparison_refuses_incomplete_or_invalid_lists(entry, arm):
    valid = {
        "meta": {"branch_coverage": True},
        "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}},
    }
    invalid = {"meta": {"branch_coverage": True}, "files": {measure.VERIFIER: entry}}
    before, after = (invalid, valid) if arm == "baseline" else (valid, invalid)
    with pytest.raises(ValueError, match=arm + ".*coverage"):
        measure.coverage_comparison(before, after)


def test_coverage_comparison_accepts_explicit_empty_lists_and_negative_exits():
    empty = {
        "meta": {"branch_coverage": True},
        "files": {measure.VERIFIER: {"executed_lines": [], "executed_branches": []}},
    }
    populated = {
        "meta": {"branch_coverage": True},
        "files": {measure.VERIFIER: {"executed_lines": [1, 2], "executed_branches": [[2, -1]]}},
    }
    assert measure.coverage_comparison(empty, empty)["lost_branches"] == []
    assert measure.coverage_comparison(populated, populated)["candidate_branches"] == 1


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize(
    "meta",
    [None, [], {}, {"branch_coverage": False}, {"branch_coverage": "true"}, {"branch_coverage": 1}],
)
def test_coverage_comparison_requires_explicit_branch_mode(arm, meta):
    # Empty arc lists alone cannot distinguish branch coverage from line-only data.
    valid = {
        "meta": {"branch_coverage": True},
        "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": []}},
    }
    invalid = {"files": valid["files"]}
    if meta is not None:
        invalid["meta"] = meta
    before, after = (invalid, valid) if arm == "baseline" else (valid, invalid)
    with pytest.raises(ValueError, match=arm + ".*branch coverage"):
        measure.coverage_comparison(before, after)


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_run_withholds_line_only_branch_comparison(tmp_path, monkeypatch, arm):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)

    def fake_pytest(command, *, cwd, **kwargs):
        _junit_receipt(cwd, name="pytest-junit.xml")
        coverage = {
            "meta": {"branch_coverage": cwd.name != arm},
            "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": []}},
        }
        (cwd / "coverage.json").write_text(json.dumps(coverage))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(measure, "packages", lambda: [])
    monkeypatch.setattr(measure.platform, "platform", lambda: "fixture-platform")
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["verifier_coverage"] is None
    assert "UNKNOWN" in result["coverage_error"]
    assert result["outcome_comparison"]["successful"] is True
    assert result["timing_comparison"]["available"] is True
    assert result["source_integrity"]["verified"] is True
    assert result["packages_unchanged"] is True
    assert all(row["exit_code"] == 0 for row in result["arms"].values())
    assert len(result["artifact_sha256"]) == 6


def _junit_receipt(tmp_path, *, name="receipt.xml", status="", omit_suite=False):
    path = tmp_path / name
    suites = measure.SUITES[:-1] if omit_suite else measure.SUITES
    path.write_text(
        '<testsuites><testsuite tests="3">'
        + "".join(
            f'<testcase classname="{suite[:-3].replace("/", ".")}" name="test_case" time="0">'
            f"{status}</testcase>"
            for suite in suites
        )
        + "</testsuite></testsuites>"
    )
    return path


@pytest.mark.parametrize(
    ("status", "outcome"),
    [("", "passed"), ("<failure/>", "failures"), ("<error/>", "errors"), ("<skipped/>", "skipped")],
)
def test_junit_retains_explicit_outcome_counts(tmp_path, status, outcome):
    receipt = measure.junit(_junit_receipt(tmp_path, status=status))
    for suite in measure.SUITES:
        row = receipt["per_file"][suite[:-3].replace("/", ".")]
        assert row["cases"] == 1
        assert row[outcome] == 1
        assert sum(row[key] for key in ("passed", "failures", "errors", "skipped")) == 1


@pytest.mark.parametrize("container", ["testsuite", "testsuites"])
@pytest.mark.parametrize(
    "attribute,value",
    [
        ("tests", "4"),
        ("tests", "2"),
        ("tests", "-1"),
        ("tests", "3.0"),
        ("tests", "unknown"),
        ("tests", ""),
        ("failures", "1"),
        ("errors", "1"),
        ("skipped", "1"),
    ],
)
def test_junit_refuses_inconsistent_declared_totals(tmp_path, container, attribute, value):
    path = _junit_receipt(tmp_path)
    text = path.read_text().replace(' tests="3"', "")
    path.write_text(text.replace(f"<{container}>", f'<{container} {attribute}="{value}">'))
    with pytest.raises(ValueError, match="JUnit.*" + attribute):
        measure.junit(path)


def test_junit_reconciles_nested_totals_and_explicit_outcomes(tmp_path):
    path = tmp_path / "nested.xml"
    path.write_text(
        '<testsuites tests="4" failures="1" errors="1" skipped="1">'
        '<testsuite tests="2" failures="1" errors="0" skipped="0">'
        '<testcase classname="first" time="0"/>'
        '<testcase classname="first" time="0"><failure/></testcase></testsuite>'
        '<testsuite tests="2" failures="0" errors="1" skipped="1">'
        '<testcase classname="second" time="0"><error/></testcase>'
        '<testcase classname="second" time="0"><skipped/></testcase></testsuite>'
        "</testsuites>"
    )
    receipt = measure.junit(path)
    assert receipt["per_file"]["first"]["cases"] == 2
    assert receipt["per_file"]["first"]["passed"] == 1
    assert receipt["per_file"]["first"]["failures"] == 1
    assert receipt["per_file"]["second"]["errors"] == 1
    assert receipt["per_file"]["second"]["skipped"] == 1


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_run_refuses_truncated_junit_even_when_every_scoped_suite_is_present(
    tmp_path, monkeypatch, arm
):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)

    def fake_pytest(command, *, cwd, **kwargs):
        receipt = _junit_receipt(cwd, name="pytest-junit.xml")
        if cwd.name == arm:
            receipt.write_text(receipt.read_text().replace('tests="3"', 'tests="4"'))
        coverage = {
            "meta": {"branch_coverage": True},
            "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}},
        }
        (cwd / "coverage.json").write_text(json.dumps(coverage))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(measure, "packages", lambda: [])
    monkeypatch.setattr(measure.platform, "platform", lambda: "fixture-platform")
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["arms"][arm]["exit_code"] == 0
    assert "UNKNOWN" in result["arms"][arm]["junit_error"]
    assert result["outcome_comparison"]["successful"] is False
    assert result["timing_comparison"]["available"] is False
    assert result["verifier_coverage"]["lost_branches"] == []
    assert len(result["arms"]) == 2
    assert len(result["artifact_sha256"]) == 6


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize(
    "defect",
    ["missing", "empty", "unreadable", "conflicting", "scope", "failure", "error", "skipped"],
)
def test_run_refuses_incomplete_or_unsuccessful_outcome_evidence(
    tmp_path, monkeypatch, arm, defect
):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)
    valid_coverage = {
        "meta": {"branch_coverage": True},
        "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}},
    }

    def fake_pytest(command, *, cwd, **kwargs):
        (cwd / "coverage.json").write_text(json.dumps(valid_coverage))
        if cwd.name != arm or defect != "missing":
            status = {"failure": "<failure/>", "error": "<error/>", "skipped": "<skipped/>"}.get(
                defect, ""
            )
            if defect == "conflicting":
                status = "<failure/><skipped/>"
            receipt = _junit_receipt(
                cwd,
                name="pytest-junit.xml",
                status=status if cwd.name == arm else "",
                omit_suite=cwd.name == arm and defect == "scope",
            )
            if cwd.name == arm and defect == "empty":
                receipt.write_text("<testsuites/>")
            elif cwd.name == arm and defect == "unreadable":
                receipt.write_text("<testsuites>")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(measure, "packages", lambda: [])
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["arms"][arm]["exit_code"] == 0
    assert result["outcome_comparison"]["successful"] is False
    assert any(arm in reason for reason in result["outcome_comparison"]["gaps"])
    assert result["artifact_sha256"]
    if defect in ("unreadable", "conflicting"):
        assert "UNKNOWN" in result["arms"][arm]["junit_error"]


@pytest.mark.parametrize("defect", ["missing", "unreadable", "invalid-lists"])
def test_run_preserves_failed_coverage_comparison_receipt(tmp_path, monkeypatch, defect):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)

    def fake_pytest(command, *, cwd, **kwargs):
        _junit_receipt(cwd, name="pytest-junit.xml")
        coverage = cwd / "coverage.json"
        if defect == "unreadable":
            coverage.write_text("{")
        elif defect == "invalid-lists":
            coverage.write_text(
                json.dumps({"meta": {"branch_coverage": True}, "files": {measure.VERIFIER: {}}})
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(measure, "packages", lambda: [])
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["verifier_coverage"] is None
    assert result["coverage_error"]
    assert result["outcome_comparison"]["successful"] is True
    assert len(result["arms"]) == 2


@pytest.mark.parametrize("failure", ["exit", "packages", "lost-lines", "lost-branches"])
def test_existing_measurement_failure_checks_remain_required(tmp_path, monkeypatch, failure):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)

    def fake_pytest(command, *, cwd, **kwargs):
        _junit_receipt(cwd, name="pytest-junit.xml")
        entry = {"executed_lines": [1, 2], "executed_branches": [[1, 2], [2, -1]]}
        if cwd.name == "candidate":
            if failure == "lost-lines":
                entry["executed_lines"] = [1]
            elif failure == "lost-branches":
                entry["executed_branches"] = [[1, 2]]
        (cwd / "coverage.json").write_text(
            json.dumps({"meta": {"branch_coverage": True}, "files": {measure.VERIFIER: entry}})
        )
        return subprocess.CompletedProcess(command, 1 if failure == "exit" else 0)

    package_reads = iter([[], [{"name": "changed"}]] if failure == "packages" else [[], []])
    monkeypatch.setattr(measure, "packages", lambda: next(package_reads))
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["outcome_comparison"]["successful"] is True
    assert result["verifier_coverage"] is not None


@pytest.mark.parametrize("duration", [None, "bad", "-1", "nan", "inf", "-inf"])
def test_junit_unknown_timing_preserves_outcomes_and_other_suite_times(tmp_path, duration):
    path = _junit_receipt(tmp_path)
    text = path.read_text()
    attribute = "" if duration is None else f'time="{duration}"'
    path.write_text(text.replace('time="0"', attribute, 1))

    receipt = measure.junit(path)
    first = receipt["per_file"][measure.SUITES[0][:-3].replace("/", ".")]
    assert first["cases"] == first["passed"] == 1
    assert first["worker_seconds"] is None
    assert first["timed_cases"] == 0
    assert first["untimed_cases"] == 1
    assert first["timing_status"] == "UNKNOWN"
    for suite in measure.SUITES[1:]:
        row = receipt["per_file"][suite[:-3].replace("/", ".")]
        assert row["worker_seconds"] == 0
        assert row["timing_status"] == "KNOWN"


def test_junit_partial_or_overflowing_timing_never_reports_a_partial_sum(tmp_path):
    path = tmp_path / "receipt.xml"
    path.write_text(
        '<testsuite><testcase classname="partial" time="2"/>'
        '<testcase classname="partial"/>'
        '<testcase classname="overflow" time="1e308"/>'
        '<testcase classname="overflow" time="1e308"/></testsuite>'
    )
    receipt = measure.junit(path)
    partial, overflow = receipt["per_file"]["partial"], receipt["per_file"]["overflow"]
    for row in (partial, overflow):
        assert row["passed"] == row["cases"] == 2
        assert row["worker_seconds"] is None
        assert row["timing_status"] == "UNKNOWN"
    assert partial["timed_cases"] == 1
    assert partial["untimed_cases"] == 1
    assert overflow["timed_cases"] == 2
    assert overflow["untimed_cases"] == 0


@pytest.mark.parametrize("duration", [None, "bad", "-1", "nan", "inf", "1e308", "0", "2.5"])
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_run_keeps_outcomes_but_refuses_unknown_scoped_timing(tmp_path, monkeypatch, arm, duration):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)

    def fake_pytest(command, *, cwd, **kwargs):
        receipt = _junit_receipt(cwd, name="pytest-junit.xml")
        if cwd.name == arm:
            text = receipt.read_text()
            attribute = "" if duration is None else f'time="{duration}"'
            # Two valid individual durations can overflow the suite's total.
            if duration == "1e308":
                suite = measure.SUITES[0][:-3].replace("/", ".")
                text = text.replace(
                    "</testsuite>", f'<testcase classname="{suite}" time="1e308"/></testsuite>'
                ).replace('tests="3"', 'tests="4"')
            receipt.write_text(text.replace('time="0"', attribute))
        coverage = {
            "meta": {"branch_coverage": True},
            "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}},
        }
        (cwd / "coverage.json").write_text(json.dumps(coverage))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(measure, "packages", lambda: [])
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    known = duration in ("0", "2.5")
    monkeypatch.setattr(measure.platform, "platform", lambda: "fixture-platform")
    assert measure.run(output) == (0 if known else 1)
    result = json.loads((output / "result.json").read_text())
    assert result["outcome_comparison"] == {"successful": True, "gaps": []}
    assert result["timing_comparison"]["available"] is known
    if not known:
        assert any(arm in gap and "UNKNOWN" in gap for gap in result["timing_comparison"]["gaps"])
    assert len(result["arms"]) == 2
    assert len(result["artifact_sha256"]) == 6
    assert "junit_error" not in result["arms"][arm]
    # Evidence JSON must never contain non-standard NaN or Infinity values.
    json.dumps(result, allow_nan=False)


def test_hosted_comparison_selects_reviewed_sources_and_requested_runtimes():
    import shlex

    import yaml

    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/maint-88-verifier-runtime-comparison.yml").read_text()
    )
    job = workflow["jobs"]["compare"]
    assert job["strategy"]["matrix"]["python"] == ["3.13", "3.14"]
    steps = job["steps"]
    prepare = next(step["run"] for step in steps if step["name"] == "Prepare immutable arms")
    args = shlex.split(prepare)
    assert args[args.index("--baseline") + 1] == "00f43f81e51c4f8b9a057ac51f7e3c2d870d7769"
    assert args[args.index("--candidate") + 1] == "8c0afc3ef0263cf85949b6167435ceabed5dd2a3"
    install = next(step for step in steps if step["name"].startswith("Install one common"))
    assert (
        install["run"]
        == "python -m pip install --requirement measurement/candidate/requirements.lock"
    )
    assert install["env"]["PIP_NO_CACHE_DIR"] == "1"
    execute = next(step for step in steps if step["name"].startswith("Run both arms"))
    assert execute["run"] == "python scripts/measure_verifier_runtime.py run --output measurement"
    assert "continue-on-error" not in execute


def _phase_receipts(arm):
    for role in ("controller", "gw0", "gw1", "gw2", "gw3"):
        path = arm / "phase-clocks" / f"{role}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "role": role,
                    "clock": "time.monotonic",
                    "boundaries": {
                        "session_start": 1,
                        "session_end": 20,
                        "collection_start": 2,
                        "collection_end": 4,
                        "loop_start": 2,
                        "loop_end": 17,
                        "coverage_reporting_start": 15,
                        "coverage_reporting_end": 17,
                        "reporting_start": 17,
                        "reporting_end": 20,
                    },
                }
            )
        )


def test_phases_measure_reporting_directly_despite_overlapping_clocks(tmp_path):
    _phase_receipts(tmp_path)
    phases = measure.execution_phases(tmp_path)
    assert phases["available"]
    assert "overlap" in phases["overlap_note"]
    assert phases["processes"]["controller"]["coverage_reporting"]["seconds"] == 2
    for process in phases["processes"].values():
        assert process["reporting"] == {"start": 17, "end": 20, "seconds": 3}
        assert process["collection"]["seconds"] == 2
        assert process["controller_worker_loop"]["seconds"] == 15


@pytest.mark.parametrize("clock", [None, True, -1, "2", float("nan"), float("inf"), 25])
def test_phases_withhold_missing_invalid_and_reversed_boundaries(tmp_path, clock):
    _phase_receipts(tmp_path)
    path = tmp_path / "phase-clocks/gw2.json"
    receipt = json.loads(path.read_text())
    receipt["boundaries"]["reporting_start"] = clock
    path.write_text(json.dumps(receipt))
    phases = measure.execution_phases(tmp_path)
    assert not phases["available"]
    assert phases["processes"]["gw2"]["reporting"] is None
    assert phases["processes"]["gw1"]["reporting"]["seconds"] == 3


@pytest.mark.parametrize("contents", [None, "{", "null", "[]", '{"role":"gw1"}'])
def test_phases_missing_receipt_is_unknown_without_inferred_remainder(tmp_path, contents):
    _phase_receipts(tmp_path)
    path = tmp_path / "phase-clocks/controller.json"
    if contents is None:
        path.unlink()
    else:
        path.write_text(contents)
    phases = measure.execution_phases(tmp_path)
    assert not phases["available"]
    assert all(value is None for value in phases["processes"]["controller"].values())
    assert phases["processes"]["gw0"]["session"]["seconds"] == 19


def test_missing_coverage_reporting_boundary_remains_unknown(tmp_path):
    _phase_receipts(tmp_path)
    path = tmp_path / "phase-clocks/controller.json"
    receipt = json.loads(path.read_text())
    del receipt["boundaries"]["coverage_reporting_end"]
    path.write_text(json.dumps(receipt))
    phases = measure.execution_phases(tmp_path)
    assert not phases["available"]
    assert phases["processes"]["controller"]["coverage_reporting"] is None
    assert phases["processes"]["controller"]["reporting"]["seconds"] == 3
