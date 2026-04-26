from scripts.repo_review_issue_quality import issue_body_is_agent_ready, issue_body_quality_errors

VALID_BODY = """## Why

The repo needs a deterministic local smoke so agents can prove the reviewed workflow instead of relying on manual inspection.

## Scope

- Add one focused smoke around the documented local path.
- Keep fixtures deterministic and offline.

## Non-Goals

- Do not add live external services.
- Do not refactor unrelated modules.

## Tasks

- [ ] Implement the smoke in `tests/test_local_smoke.py` using existing public APIs.
- [ ] Add fixture data under `tests/fixtures/local_smoke/` that exercises the reviewed path.
- [ ] Assert the smoke fails when the primary output object is missing.
- [ ] Document the smoke command in `docs/local-testing.md`.

## Acceptance Criteria

- [ ] `python -m pytest tests/test_local_smoke.py --no-cov` exits zero with local fixtures.
- [ ] The smoke fails with a clear assertion if the primary output object is not created.
- [ ] Documentation names the command and the fixture data used by the smoke.

## Implementation Notes

Relevant files: `tests/test_local_smoke.py`, `tests/fixtures/local_smoke/`, `docs/local-testing.md`.
"""


def test_agent_ready_issue_body_passes_quality_gate() -> None:
    assert issue_body_is_agent_ready(VALID_BODY)
    assert issue_body_quality_errors(VALID_BODY) == []


def test_generic_weekly_review_boilerplate_is_rejected() -> None:
    body = VALID_BODY.replace(
        "Implement the smoke in `tests/test_local_smoke.py` using existing public APIs.",
        "Implement the approved review gap: Add a smoke test.",
    ).replace(
        "The smoke fails with a clear assertion if the primary output object is not created.",
        "The reviewed design/readiness gap is implemented in repo-local code, docs, tests, or workflows as appropriate for the issue.",
    )

    errors = issue_body_quality_errors(body)

    assert any("generic placeholder phrase" in error for error in errors)


def test_fragment_checkboxes_are_rejected() -> None:
    body = VALID_BODY.replace(
        "Implement the smoke in `tests/test_local_smoke.py` using existing public APIs.",
        "Implement `canonicalize_name()`:",
    )

    errors = issue_body_quality_errors(body)

    assert any("fragment ending with colon" in error for error in errors)


def test_broad_implementation_notes_are_rejected() -> None:
    body = VALID_BODY.replace(
        "Relevant files: `tests/test_local_smoke.py`, `tests/fixtures/local_smoke/`, `docs/local-testing.md`.",
        "Relevant areas: `src/`, `tests/`, `docs/`.",
    )

    errors = issue_body_quality_errors(body)

    assert any("Relevant areas" in error for error in errors)
