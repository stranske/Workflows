"""Exercise the published Health 67 CI comparison without any GitHub writes."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/health-67-integration-sync-check.yml"
CI = Path(".github/workflows/ci.yml")

pytestmark = pytest.mark.skipif(
    not (shutil.which("yq") and shutil.which("jq")), reason="Health 67 uses the runner's yq and jq"
)


def _compare_ci(tmp_path, template, actual):
    for relative, text in (
        (Path("workflows/templates/integration-repo") / CI, template),
        (Path("integration-tests") / CI, actual),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["check-sync"]["steps"]
    compare = next(step["run"] for step in steps if step.get("id") == "compare-ci")
    output = tmp_path / "outputs"
    output.touch()
    summary = tmp_path / "summary"
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", compare],
        cwd=tmp_path,
        env={
            **os.environ,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        check=True,
        timeout=10,
    )
    return output.read_text(encoding="utf-8"), summary.read_text(encoding="utf-8")


@pytest.fixture
def template():
    return (ROOT / "templates/integration-repo" / CI).read_text(encoding="utf-8")


@pytest.fixture
def receiver(template):
    return template.replace(
        "__WORKFLOW_REF__", "stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main"
    )


def test_health_67_accepts_matching_prefixes_and_unprefixed_job(tmp_path, template, receiver):
    jobs = yaml.safe_load(receiver)["jobs"]
    assert "artifact-prefix" not in jobs["notify-failure"].get("with", {})
    output, summary = _compare_ci(
        tmp_path, template, receiver.replace("artifact-prefix: basic-", "artifact-prefix: 'basic-'")
    )
    assert not output
    assert "Artifact prefixes match by job" in summary


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("artifact-prefix: basic-", "# artifact-prefix: basic-", '["basic","basic-"]'),
        (
            "artifact-prefix: full-",
            "artifact-prefix: wrongly-routed-",
            '["full-coverage","wrongly-routed-"]',
        ),
        ("artifact-prefix: typecheck-", "artifact-prefix: ''", '["typecheck-only","typecheck-"]'),
    ],
)
def test_health_67_detects_prefix_drift_by_job(
    tmp_path, template, receiver, before, after, expected
):
    assert receiver.count(before) == 1
    output, summary = _compare_ci(tmp_path, template, receiver.replace(before, after))
    assert output == "drift=true\n"
    assert "Artifact prefixes differ by job" in summary
    assert expected in summary


def test_health_67_detects_swapped_prefixes(tmp_path, template, receiver):
    swapped = re.sub(
        r"artifact-prefix: (basic-|full-)",
        lambda match: "artifact-prefix: " + {"basic-": "full-", "full-": "basic-"}[match[1]],
        receiver,
    )
    output, summary = _compare_ci(tmp_path, template, swapped)
    assert output == "drift=true\n"
    assert '["basic","full-"]' in summary
    assert '["full-coverage","basic-"]' in summary


def test_health_67_preserves_missing_template_prefix_guard(tmp_path, template, receiver):
    no_prefixes = re.sub(r"^      artifact-prefix: .*\n", "", template, flags=re.M)
    assert template != no_prefixes
    output, summary = _compare_ci(tmp_path, no_prefixes, receiver)
    assert output == "drift=true\n"
    assert "Template missing artifact-prefix" in summary


def test_health_67_detects_prefix_on_unexpected_job(tmp_path, template, receiver):
    new_route = receiver.replace(
        "  notify-failure:\n", "  notify-failure:\n    with:\n      artifact-prefix: unexpected-\n"
    )
    output, summary = _compare_ci(tmp_path, template, new_route)
    assert output == "drift=true\n"
    assert '["notify-failure","unexpected-"]' in summary


@pytest.mark.parametrize(
    ("after", "expected_error"),
    [
        ("artifact-prefix: false", "Expected string artifact prefixes"),
        ("artifact-prefix: [", "Expected one jobs mapping"),
    ],
)
def test_health_67_fails_on_unusable_prefix_data(
    tmp_path, template, receiver, capfd, after, expected_error
):
    with pytest.raises(subprocess.CalledProcessError):
        _compare_ci(tmp_path, template, receiver.replace("artifact-prefix: basic-", after))
    assert expected_error in capfd.readouterr().err


def test_health_67_fails_on_multiple_yaml_documents(tmp_path, template, receiver, capfd):
    with pytest.raises(subprocess.CalledProcessError):
        _compare_ci(tmp_path, template, receiver + "\n---\njobs: {}\n")
    assert "Expected one jobs mapping" in capfd.readouterr().err
