"""Static guard: the reusable agent runner workflows share a single setup
surface via the ``agent-run-base`` composite action.

Background — why this test exists
=================================
Issue #2341: ``reusable-claude-run.yml`` and ``reusable-codex-run.yml`` carried
~684 duplicated lines and had **already started diverging** — e.g. the claude
runner gained the ``@octokit/rest`` blobless-clone guard while codex kept its
own ``codex_jsonl_parser`` handling, and the reference-pack heredoc broke in one
runner but not the other (#2263 / #2287). Every shared-step fix had to be
applied twice.

PR #2345 extracted the reference-pack materializer into
``.github/actions/agent-reference-packs``. This follow-up extracts the
agent-agnostic *setup* block — checkout of the target repo, Node.js setup, the
API client, and the ``.workflows-lib`` scripts checkout — into
``.github/actions/agent-run-base`` so it is maintained in one place.

This test asserts both runners call the shared composite exactly once and no
longer carry their own copy of the extracted ``actions/checkout`` /
``sparse-checkout`` steps, so the duplication cannot silently creep back.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

REUSABLE_RUN_WORKFLOWS = [
    ".github/workflows/reusable-codex-run.yml",
    ".github/workflows/reusable-claude-run.yml",
]
RUN_BASE_ACTION = ".github/actions/agent-run-base/action.yml"
RUN_BASE_CHECKOUT_PATH = ".workflows-actions"
RUN_BASE_USE_BASES = {
    f"./{RUN_BASE_CHECKOUT_PATH}/.github/actions/agent-run-base",
    "stranske/Workflows/.github/actions/agent-run-base",
}

# Step names the composite must run, in order. Behaviour parity with the
# pre-extraction inline block depends on this exact sequence.
EXPECTED_STEP_NAMES = [
    "Checkout",
    "Set up Node.js",
    "Setup API client",
    "Checkout Workflows scripts",
]


def _workflow_steps(workflow_rel: str) -> list[dict]:
    data = yaml.safe_load((ROOT / workflow_rel).read_text())
    jobs = data["jobs"]
    job = jobs[next(iter(jobs))]
    return [step for step in job["steps"] if isinstance(step, dict)]


def _uses_base(step: dict) -> str:
    return str(step.get("uses") or "").split("@", 1)[0]


def test_run_base_action_exists_and_parses() -> None:
    path = ROOT / RUN_BASE_ACTION
    assert path.exists(), f"missing action file: {RUN_BASE_ACTION}"

    data = yaml.safe_load(path.read_text())
    assert (
        data.get("runs", {}).get("using") == "composite"
    ), f"{RUN_BASE_ACTION}: expected a composite action"

    steps = data["runs"]["steps"]
    names = [s.get("name") for s in steps]
    assert names == EXPECTED_STEP_NAMES, (
        f"{RUN_BASE_ACTION}: step sequence drifted from the extracted block; "
        f"got {names}, expected {EXPECTED_STEP_NAMES}"
    )

    # The shared block must still reach setup-api-client and the sparse
    # Workflows scripts checkout — the whole point of the extraction.
    src = path.read_text()
    assert "uses: ./.github/actions/setup-api-client" in src
    assert "sparse-checkout" in src


@pytest.mark.parametrize("workflow_rel", REUSABLE_RUN_WORKFLOWS)
def test_reusable_runners_use_shared_run_base(workflow_rel: str) -> None:
    path = ROOT / workflow_rel
    assert path.exists(), f"missing workflow file: {workflow_rel}"

    steps = _workflow_steps(workflow_rel)
    run_base_calls = sum(1 for step in steps if _uses_base(step) in RUN_BASE_USE_BASES)
    assert (
        run_base_calls == 1
    ), f"{workflow_rel}: must call the shared agent-run-base composite exactly once"


@pytest.mark.parametrize("workflow_rel", REUSABLE_RUN_WORKFLOWS)
def test_extracted_setup_steps_not_duplicated_in_runners(workflow_rel: str) -> None:
    path = ROOT / workflow_rel
    src = path.read_text()
    steps = _workflow_steps(workflow_rel)
    run_base_checkout_steps = [
        step
        for step in steps
        if step.get("name") == "Checkout Workflows run-base action"
        and _uses_base(step) == "actions/checkout"
    ]

    assert len(run_base_checkout_steps) == 1, (
        f"{workflow_rel}: expected one pre-checkout for {RUN_BASE_ACTION} so "
        "the local composite exists before the target repository checkout"
    )
    checkout_with = run_base_checkout_steps[0]["with"]
    assert checkout_with["path"] == RUN_BASE_CHECKOUT_PATH
    assert ".github/actions/agent-run-base" in checkout_with["sparse-checkout"]

    # The target repository checkout and Workflows scripts checkout now live in
    # the composite; only the pre-checkout for the composite definition remains
    # in the runners.
    assert "repository: stranske/Workflows" in src
    assert "path: .workflows-lib" not in src, (
        f"{workflow_rel}: the .workflows-lib sparse checkout was extracted to "
        f"{RUN_BASE_ACTION}; it should not reappear verbatim in the runner"
    )
    # The remaining setup-api-client call is the .workflows-lib one (install_dir);
    # the bare one was extracted, so exactly one reference should remain.
    assert src.count("uses: ./.github/actions/setup-api-client") == 1, (
        f"{workflow_rel}: expected exactly one setup-api-client call to remain "
        "(the .workflows-lib install); the bare call was extracted"
    )
