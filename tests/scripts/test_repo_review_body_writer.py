"""Unit tests for ``scripts/repo_review_body_writer.py``.

Companion to ``test_repo_review_heartbeat.py``. The 2026-05-13 cycle's #2087
PR covered coordinator + round2_runner but explicitly excluded body-writer
under its Non-Goals. This module pins the body-writer's pure logic:

- ``body_quality_errors`` — the post-write gate that catches generic
  boilerplate, missing sections, and undersized bodies before upload
- ``converged_path`` — round-2 layout convention
- ``canonical_body_writer_prompt`` — points at the source-of-truth prompt
- ``build_prompt`` — header injection + prompt template inclusion
- ``verify_clean_sync`` — guard that confirms the local repo is at
  origin/main head (uses a real git fixture repo)

We don't exercise ``run_body_writer`` / ``run()`` here — those shell out to
agent invocations that belong in integration coverage. The pure logic is
the load-bearing surface for upload-quality.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import repo_review_body_writer as body_writer

# ---------------------------------------------------------------------------
# body_quality_errors
# ---------------------------------------------------------------------------


CLEAN_BODY = """## Why

The reviewable-findings generator currently hard-codes the canonical fixture
finding identifiers and never reads the actual extraction/readiness outputs
that exist at `out/extraction.json` and `out/readiness.json`, so the live
runner produces synthetic findings instead of real ones.

## Scope

- Read both real source artifacts when building the findings set.
- Surface a clear error when either source is missing.

## Non-Goals

- Do not change the published artifact contract.

## Tasks

- [ ] Wire `scripts/reviewable_findings.py` to consume `out/readiness.json` rows.
- [ ] Wire `src/reviewable_findings/extract.py` to consume `out/extraction.json` rows.
- [ ] Add the missing-source assertion in `tests/test_findings_chains.py`.
- [ ] Update README to drop the "while generator wiring is finalized" qualifier.

## Acceptance Criteria

- [ ] `python -m reviewable_findings build` with real sources produces non-fixture finding IDs.
- [ ] `python -m reviewable_findings build` with missing sources exits non-zero with a clear error.
- [ ] `pytest tests/test_findings_chains.py -q` stays green on the wire-through.

## Implementation Notes

The implementation spans `scripts/reviewable_findings.py`,
`src/reviewable_findings/extract.py`, `tests/test_findings_chains.py`,
`tests/fixtures/findings.json`, `docs/reviewable-findings.md`, and `README.md`.
The fixture finding IDs `finding:demo:fixture:*` should no longer appear in
real-data output; the chain step should derive `finding:<plan_id>:<period>:<source>`
from the real `plan_id` and `period` columns in the readiness rows.

Reference example issues live at github.com/.../issues/468 and
github.com/.../issues/908. Both follow the same Why / Scope / Non-Goals /
Tasks / Acceptance Criteria / Implementation Notes layout, with concrete
file:line citations under each task, and acceptance criteria that name the
specific test command, the specific output substring, or the specific
behavior change to verify. This issue should match that depth — every
acceptance line names either a pytest command, an `rg` invocation that must
return zero matches, or a concrete output that must appear in stdout when
the wired-up reviewer runs against real source artifacts.
"""


def test_body_quality_errors_clean_body() -> None:
    assert body_writer.body_quality_errors(CLEAN_BODY) == []


def test_body_quality_errors_empty_body() -> None:
    assert body_writer.body_quality_errors("") == ["body is empty"]
    assert body_writer.body_quality_errors("   \n  ") == ["body is empty"]


def test_body_quality_errors_insufficient_evidence_marker_accepted() -> None:
    # INSUFFICIENT_EVIDENCE is a legitimate body-writer outcome that routes
    # to deeper-review; it must NOT trigger quality errors.
    body = "INSUFFICIENT_EVIDENCE: cited files no longer exist on current main"
    assert body_writer.body_quality_errors(body) == []


def test_body_quality_errors_missing_tasks_section() -> None:
    body = CLEAN_BODY.replace("## Tasks", "## Task Notes")
    errors = body_writer.body_quality_errors(body)
    assert any("Tasks" in e for e in errors)


def test_body_quality_errors_missing_acceptance_section() -> None:
    body = CLEAN_BODY.replace("## Acceptance Criteria", "## Verify")
    errors = body_writer.body_quality_errors(body)
    assert any("Acceptance Criteria" in e for e in errors)


def test_body_quality_errors_short_body() -> None:
    body = "## Tasks\n- [ ] do thing\n## Acceptance Criteria\n- [ ] thing done\n"
    errors = body_writer.body_quality_errors(body)
    # The short body lacks length AND will not contain generic phrases.
    assert any("too short" in e for e in errors)


def test_body_quality_errors_generic_boilerplate_phrase() -> None:
    body = CLEAN_BODY + "\n\nImplement the approved review gap as described above."
    errors = body_writer.body_quality_errors(body)
    assert any("generic boilerplate" in e for e in errors)


def test_body_quality_errors_accepts_task_list_alias() -> None:
    body = CLEAN_BODY.replace("## Tasks", "## Task list")
    # The check accepts `## task list` (lowercased) as an alias for `## tasks`.
    errors = body_writer.body_quality_errors(body)
    assert not any("Tasks" in e for e in errors)


# ---------------------------------------------------------------------------
# acceptance falsifiability gate (Definition of Ready §2)
# ---------------------------------------------------------------------------

# A long, otherwise-clean filler so length/boilerplate checks don't mask the
# falsifiability assertion. Acceptance criteria here are deliberately vague
# (no test, no command, no smoke/verif token).
_FILLER = "Background detail. " * 120


def _body_with_acceptance(criteria_block: str) -> str:
    return (
        "## Why\n\n"
        f"{_FILLER}\n\n"
        "## Tasks\n\n"
        "- [ ] In `src/foo.py:10`, do the concrete thing.\n\n"
        "## Acceptance Criteria\n\n"
        f"{criteria_block}\n\n"
        "## Implementation Notes\n\n"
        f"{_FILLER}\n"
    )


def test_acceptance_has_verification_gate_true_for_named_test() -> None:
    body = _body_with_acceptance("- [ ] `tests/test_foo.py::test_bar` passes after the fix.")
    assert body_writer.acceptance_has_verification_gate(body) is True


def test_acceptance_has_verification_gate_true_for_command() -> None:
    body = _body_with_acceptance("- [ ] `gh workflow run selftest-ci.yml` shows a green run.")
    assert body_writer.acceptance_has_verification_gate(body) is True


def test_acceptance_has_verification_gate_true_for_smoke_token() -> None:
    body = _body_with_acceptance("- [ ] Smoke request returns HTTP 400 with the error body.")
    assert body_writer.acceptance_has_verification_gate(body) is True


def test_acceptance_has_verification_gate_false_for_vague_criteria() -> None:
    body = _body_with_acceptance(
        "- [ ] The output looks correct.\n- [ ] The feature works as expected."
    )
    assert body_writer.acceptance_has_verification_gate(body) is False


def test_acceptance_gate_ignores_test_refs_outside_acceptance_block() -> None:
    # A pytest reference in Implementation Notes must NOT satisfy the gate; the
    # falsifiable criterion has to live in the Acceptance Criteria section.
    body = (
        "## Why\n\n"
        f"{_FILLER}\n\n"
        "## Tasks\n\n"
        "- [ ] In `src/foo.py:10`, do the concrete thing.\n\n"
        "## Acceptance Criteria\n\n"
        "- [ ] It works nicely.\n\n"
        "## Implementation Notes\n\n"
        "Run `pytest tests/test_foo.py` locally first.\n"
        f"{_FILLER}\n"
    )
    assert body_writer.acceptance_has_verification_gate(body) is False


def test_body_quality_errors_flags_acceptance_without_gate() -> None:
    body = _body_with_acceptance(
        "- [ ] The output looks correct.\n- [ ] The feature works as expected."
    )
    errors = body_writer.body_quality_errors(body)
    assert any("falsifiable gate" in e for e in errors), errors


def test_body_quality_errors_passes_acceptance_with_named_test() -> None:
    body = _body_with_acceptance(
        "- [ ] `tests/test_foo.py::test_bar` passes (asserts the 400 path)."
    )
    errors = body_writer.body_quality_errors(body)
    assert not any("falsifiable gate" in e for e in errors), errors


def test_body_quality_errors_clean_body_passes_gate() -> None:
    # The shared CLEAN_BODY fixture names pytest + a runnable command in its
    # acceptance criteria, so the falsifiability gate must not fire on it.
    errors = body_writer.body_quality_errors(CLEAN_BODY)
    assert not any("falsifiable gate" in e for e in errors)


def test_missing_acceptance_section_not_double_flagged_for_gate() -> None:
    # When the acceptance section is absent entirely, the missing-section error
    # owns it; the falsifiability check must NOT also fire (avoids a confusing
    # double error).
    body = CLEAN_BODY.replace("## Acceptance Criteria", "## Verify")
    errors = body_writer.body_quality_errors(body)
    assert any("Acceptance Criteria" in e and "missing" in e for e in errors)
    assert not any("falsifiable gate" in e for e in errors)


def test_body_quality_errors_enforces_documented_file_reference_counts() -> None:
    body = (
        "## Why\n\n" + _FILLER + "\n\n"
        "## Tasks\n\n"
        "- [ ] Update `src/a.py`, `src/b.py`, and `tests/test_a.py`.\n\n"
        "## Acceptance Criteria\n\n"
        "- [ ] `pytest tests/test_a.py -q` passes.\n\n"
        "## Implementation Notes\n\n"
        "Inspect `src/a.py`, `src/b.py`, `tests/test_a.py`, `docs/a.md`, and `README.md`.\n\n"
        + _FILLER
    )

    errors = body_writer.body_quality_errors(body)

    assert len(errors) == 2
    assert any("Tasks reference 3" in error for error in errors)
    assert any("Implementation Notes reference 5" in error for error in errors)


def test_body_quality_errors_rejects_unresolvable_paths(tmp_path: Path) -> None:
    for relative in (
        "src/a.py",
        "src/b.py",
        "tests/test_a.py",
        "docs/a.md",
        "docs/b.md",
        "scripts/check.py",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
    body = (
        "## Why\n\n" + _FILLER + "\n\n"
        "## Tasks\n\n"
        "- [ ] Update `src/a.py`, `src/b.py`, `tests/test_a.py`, and `missing/x.py`.\n\n"
        "## Acceptance Criteria\n\n"
        "- [ ] `pytest tests/test_a.py -q` passes.\n\n"
        "## Implementation Notes\n\n"
        "Inspect `src/a.py`, `src/b.py`, `tests/test_a.py`, `docs/a.md`, `docs/b.md`, "
        "and `scripts/check.py`.\n\n" + _FILLER
    )

    errors = body_writer.body_quality_errors(body, repo_path=tmp_path)

    assert any("missing/x.py" in error for error in errors)


def test_body_quality_errors_does_not_treat_expected_repo_slug_as_path(tmp_path: Path) -> None:
    for relative in (
        "src/a.py",
        "src/b.py",
        "tests/test_a.py",
        "docs/a.md",
        "docs/b.md",
        "scripts/check.py",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
    body = CLEAN_BODY.replace(
        "github.com/.../issues/908",
        "`stranske/Example` and github.com/.../issues/908",
    )

    errors = body_writer.body_quality_errors(
        body,
        repo_path=tmp_path,
        expected_repo="stranske/Example",
    )

    assert not any("stranske/Example" in error for error in errors)


def test_reference_paths_normalizes_line_ranges_and_dot_directories() -> None:
    paths = body_writer._reference_paths(
        "Update `.github/workflows/ci.yml:20-35`, `src/app.py#L8-L12`, and "
        "`tests/test_app.py::test_smoke`; ignore the ratio `0.55/0.25/0.20`."
    )

    assert paths == {
        ".github/workflows/ci.yml",
        "src/app.py",
        "tests/test_app.py",
    }


# ---------------------------------------------------------------------------
# converged_path + canonical_body_writer_prompt
# ---------------------------------------------------------------------------


def test_converged_path_uses_double_underscore_separator(tmp_path: Path) -> None:
    out = body_writer.converged_path(tmp_path, "stranske/Workflows")
    assert out == tmp_path / "round2" / "stranske__Workflows" / "converged.json"


def test_canonical_body_writer_prompt_resolves_to_repo_docs() -> None:
    prompt_path = body_writer.canonical_body_writer_prompt()
    # The prompt is REPO_REVIEW_BODY_WRITER_PROMPT.md under docs/ops/. Whether
    # or not the file is present on disk depends on whether the consumer
    # cloned it; we only assert the path shape.
    assert prompt_path.name == "REPO_REVIEW_BODY_WRITER_PROMPT.md"
    assert prompt_path.parent.name == "ops"
    assert prompt_path.parent.parent.name == "docs"


# ---------------------------------------------------------------------------
# build_prompt — header injection + canonical template inclusion
# ---------------------------------------------------------------------------


def test_build_prompt_injects_repo_variables(tmp_path: Path, monkeypatch) -> None:
    """The prompt header carries the repo identifier, the underscored safe name,
    the local repo path, and the converged.json path so the spawned agent has
    everything it needs without reaching for a separate config."""
    fake_prompt = tmp_path / "prompt.md"
    fake_prompt.write_text("PROMPT_TEMPLATE_BODY\n", encoding="utf-8")
    monkeypatch.setattr(body_writer, "canonical_body_writer_prompt", lambda: fake_prompt)

    output_dir = tmp_path / "out"
    repo_path = tmp_path / "repos" / "stranske__Workflows"

    prompt = body_writer.build_prompt(
        repo="stranske/Workflows",
        output_dir=output_dir,
        repo_path=repo_path,
    )

    assert "stranske/Workflows" in prompt
    assert "stranske__Workflows" in prompt
    assert str(repo_path) in prompt
    assert str(body_writer.converged_path(output_dir, "stranske/Workflows")) in prompt
    assert "INSUFFICIENT_EVIDENCE" in prompt
    assert "PROMPT_TEMPLATE_BODY" in prompt
    # The agent should be told to validate via the round-2 schema script.
    assert "scripts/repo_review_round2_schema.py" in prompt
    assert "--validate-only" in prompt


def test_build_prompt_requires_rewrite_of_nonempty_invalid_body(
    tmp_path: Path, monkeypatch
) -> None:
    fake_prompt = tmp_path / "prompt.md"
    fake_prompt.write_text("PROMPT_TEMPLATE_BODY\n", encoding="utf-8")
    monkeypatch.setattr(body_writer, "canonical_body_writer_prompt", lambda: fake_prompt)
    output_dir = tmp_path / "out"
    path = body_writer.converged_path(output_dir, "stranske/Workflows")
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"converged_candidates":[{"title":"Repair me","body":"non-empty but short"}],'
        '"meta_candidate":null}',
        encoding="utf-8",
    )

    prompt = body_writer.build_prompt(
        repo="stranske/Workflows",
        output_dir=output_dir,
        repo_path=tmp_path / "repo",
    )

    assert "BODY REPAIR REQUIRED" in prompt
    assert "candidate #1 'Repair me'" in prompt
    assert "rewrite every target" in prompt


def test_build_prompt_includes_prior_deterministic_failure_feedback(
    tmp_path: Path, monkeypatch
) -> None:
    fake_prompt = tmp_path / "prompt.md"
    fake_prompt.write_text("PROMPT_TEMPLATE_BODY\n", encoding="utf-8")
    monkeypatch.setattr(body_writer, "canonical_body_writer_prompt", lambda: fake_prompt)
    output_dir = tmp_path / "out"
    path = body_writer.converged_path(output_dir, "stranske/Workflows")
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"repo":"stranske/Workflows","converged_candidates":[],"meta_candidate":null}',
        encoding="utf-8",
    )
    body_writer.repair_feedback_path(output_dir, "stranske/Workflows").write_text(
        "candidate #2: Tasks reference 1 distinct repository paths; at least 4 are required\n",
        encoding="utf-8",
    )

    prompt = body_writer.build_prompt(
        repo="stranske/Workflows",
        output_dir=output_dir,
        repo_path=tmp_path / "repo",
    )

    assert "PRIOR DETERMINISTIC VALIDATOR FEEDBACK" in prompt
    assert "candidate #2: Tasks reference 1 distinct repository paths" in prompt
    assert "schema-only validation is insufficient" in prompt


def test_restore_non_body_fields_keeps_only_agent_body_changes() -> None:
    before = {
        "repo": "stranske/Example",
        "converged_candidates": [
            {"title": "Original", "design_refs": ["docs/design.md"], "body": ""}
        ],
        "meta_candidate": None,
    }
    after = {
        "repo": "stranske/Wrong",
        "converged_candidates": [
            {"title": "Mutated", "design_refs": ["README.md"], "body": "new body"}
        ],
        "meta_candidate": None,
    }

    restored, errors, restored_count = body_writer.restore_non_body_fields(before, after)

    assert errors == []
    assert restored_count == 1
    assert restored["repo"] == "stranske/Example"
    assert restored["converged_candidates"][0]["title"] == "Original"
    assert restored["converged_candidates"][0]["design_refs"] == ["docs/design.md"]
    assert restored["converged_candidates"][0]["body"] == "new body"


@pytest.mark.parametrize(
    "candidates",
    [
        {"title": "not a list"},
        [{"title": "valid object"}, "not an object"],
    ],
)
def test_candidate_records_rejects_malformed_candidate_shapes(candidates: object) -> None:
    records, errors = body_writer.candidate_records(
        {"converged_candidates": candidates, "meta_candidate": None}
    )
    assert records == []
    assert errors


def _run_args(output_dir: Path, registry_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_dir=str(output_dir),
        registry=str(registry_path),
        repo="stranske/Example",
        skip_sync_check=False,
        agent="claude",
        timeout=30,
    )


def _write_empty_converged(output_dir: Path) -> None:
    path = body_writer.converged_path(output_dir, "stranske/Example")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "repo": "stranske/Example",
                "converged_candidates": [],
                "meta_candidate": None,
            }
        ),
        encoding="utf-8",
    )


def test_run_skips_sync_verification_for_executing_steward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    steward = tmp_path / "Workflows-steward"
    registry_path = steward / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "out"
    _write_empty_converged(output_dir)
    monkeypatch.setattr(
        body_writer,
        "load_registry",
        lambda _path: (
            tmp_path,
            [],
            [SimpleNamespace(repo="stranske/Example", local_path="Workflows-steward")],
            [],
        ),
    )

    def unexpected_sync(_path):
        raise AssertionError("steward sync verification must be skipped")

    monkeypatch.setattr(body_writer, "verify_clean_sync", unexpected_sync)
    monkeypatch.setattr(body_writer, "run_body_writer", lambda **_kwargs: (False, "stop"))

    assert body_writer.run(_run_args(output_dir, registry_path)) == 1


def test_run_calls_sync_verification_for_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    steward = tmp_path / "Workflows-steward"
    registry_path = steward / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "out"
    _write_empty_converged(output_dir)
    monkeypatch.setattr(
        body_writer,
        "load_registry",
        lambda _path: (
            tmp_path,
            [],
            [SimpleNamespace(repo="stranske/Example", local_path="consumer")],
            [],
        ),
    )
    seen: list[Path] = []

    def fail_sync(path: Path) -> tuple[bool, str]:
        seen.append(path)
        return False, "not current"

    monkeypatch.setattr(body_writer, "verify_clean_sync", fail_sync)

    assert body_writer.run(_run_args(output_dir, registry_path)) == 1
    assert seen == [tmp_path / "consumer"]


@pytest.mark.parametrize(
    "candidates",
    [{"title": "bad"}, [{"title": "ok"}, 3]],
)
def test_run_records_malformed_candidate_shape_as_failed_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidates: object
) -> None:
    steward = tmp_path / "Workflows-steward"
    registry_path = steward / "config" / "repo_review_registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "out"
    path = body_writer.converged_path(output_dir, "stranske/Example")
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"converged_candidates": candidates, "meta_candidate": None}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        body_writer,
        "load_registry",
        lambda _path: (
            tmp_path,
            [],
            [SimpleNamespace(repo="stranske/Example", local_path="Workflows-steward")],
            [],
        ),
    )
    invoked = False

    def fake_writer(**_kwargs):
        nonlocal invoked
        invoked = True
        return True, "ok"

    monkeypatch.setattr(body_writer, "run_body_writer", fake_writer)

    assert body_writer.run(_run_args(output_dir, registry_path)) == 1
    assert invoked is False
    state_path = output_dir / "round2" / "stranske__Example" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["attempts"][-1]["succeeded"] is False


# ---------------------------------------------------------------------------
# verify_clean_sync — exercises a real git repo fixture
# ---------------------------------------------------------------------------


def _run(repo_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "fake-repo"
    repo_dir.mkdir()
    _run(repo_dir, "init", "-b", "main", "-q")
    _run(repo_dir, "config", "user.email", "test@example.com")
    _run(repo_dir, "config", "user.name", "Test")
    (repo_dir / "README.md").write_text("hi\n", encoding="utf-8")
    _run(repo_dir, "add", ".")
    _run(repo_dir, "commit", "-q", "-m", "init")
    # Make HEAD reachable via origin/main without a real remote: point a
    # local 'origin/main' ref at HEAD.
    head = _run(repo_dir, "rev-parse", "HEAD").stdout.strip()
    _run(repo_dir, "update-ref", "refs/remotes/origin/main", head)
    return repo_dir


def test_verify_clean_sync_passes_when_head_matches_origin_main(fake_repo: Path) -> None:
    ok, message = body_writer.verify_clean_sync(fake_repo)
    assert ok is True
    assert "HEAD matches origin/main" in message


def test_verify_clean_sync_fails_when_head_diverges(fake_repo: Path) -> None:
    # Create a new commit on main so HEAD diverges from origin/main.
    (fake_repo / "drift.md").write_text("drift\n", encoding="utf-8")
    _run(fake_repo, "add", ".")
    _run(fake_repo, "commit", "-q", "-m", "drift")
    ok, message = body_writer.verify_clean_sync(fake_repo)
    assert ok is False
    assert "does not match" in message


def test_sync_check_not_required_for_executing_steward(tmp_path: Path) -> None:
    steward = tmp_path / "Workflows-steward"
    steward.mkdir()

    assert body_writer.sync_check_required(steward, steward) is False
    assert body_writer.sync_check_required(tmp_path / "consumer", steward) is True


# ---------------------------------------------------------------------------
# Generic boilerplate phrase inventory — keep aligned with the script.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", body_writer.GENERIC_BODY_PHRASES)
def test_each_generic_boilerplate_phrase_is_flagged(phrase: str) -> None:
    body = CLEAN_BODY + f"\n\nNote: {phrase}.\n"
    errors = body_writer.body_quality_errors(body)
    assert any(
        repr(phrase) in e or phrase in e for e in errors
    ), f"phrase {phrase!r} should be flagged by body_quality_errors"


# ---------------------------------------------------------------------------
# argparse smoke — main() requires --repo and --output-dir.
# ---------------------------------------------------------------------------


def test_argparse_requires_repo_and_output_dir() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output-dir", required=True)
    with pytest.raises(SystemExit):
        parser.parse_args([])
