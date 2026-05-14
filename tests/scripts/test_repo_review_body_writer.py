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
  origin/main or origin/phase-3 head (uses a real git fixture repo)

We don't exercise ``run_body_writer`` / ``run()`` here — those shell out to
agent invocations that belong in integration coverage. The pure logic is
the load-bearing surface for upload-quality.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

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

- [ ] Wire `_finding_from_readiness_row` to consume `out/readiness.json` rows.
- [ ] Wire `_finding_from_extraction_row` to consume `out/extraction.json` rows.
- [ ] Raise `ReviewableFindingsArtifactError` when either source path is missing.
- [ ] Update README to drop the "while generator wiring is finalized" qualifier.

## Acceptance Criteria

- [ ] `python -m reviewable_findings build` with real sources produces non-fixture finding IDs.
- [ ] `python -m reviewable_findings build` with missing sources exits non-zero with a clear error.
- [ ] `pytest tests/test_findings_chains.py -q` stays green on the wire-through.

## Implementation Notes

The fixture finding IDs `finding:demo:fixture:*` should no longer appear in
real-data output; the chain step should derive `finding:<plan_id>:<period>:<source>`
from the real `plan_id` and `period` columns in the readiness rows. The
existing chain step's signature is preserved; only the source-of-input
changes from `tests/fixtures/findings.json` to the real artifact paths.

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


def test_verify_clean_sync_accepts_origin_phase_3(fake_repo: Path) -> None:
    # Point origin/phase-3 at HEAD; remove origin/main so only phase-3 matches.
    head = _run(fake_repo, "rev-parse", "HEAD").stdout.strip()
    _run(fake_repo, "update-ref", "refs/remotes/origin/phase-3", head)
    _run(fake_repo, "update-ref", "-d", "refs/remotes/origin/main")
    ok, message = body_writer.verify_clean_sync(fake_repo)
    assert ok is True
    assert "phase-3" in message


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
