import json
from pathlib import Path

from scripts import upload_repo_review_issues as uploader

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


def test_load_queue_returns_issue_list(tmp_path: Path) -> None:
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps({"issues": [{"repo": "owner/repo", "title": "Do work", "body": VALID_BODY}]}),
        encoding="utf-8",
    )

    assert uploader.load_queue(queue) == [
        {"repo": "owner/repo", "title": "Do work", "body": VALID_BODY}
    ]


def test_load_queue_rejects_generic_issue_body(tmp_path: Path) -> None:
    queue = tmp_path / "queue.json"
    bad_body = VALID_BODY.replace(
        "Implement the smoke in `tests/test_local_smoke.py` using existing public APIs.",
        "Implement the approved review gap: Add a smoke test.",
    )
    queue.write_text(
        json.dumps({"issues": [{"repo": "owner/repo", "title": "Do work", "body": bad_body}]}),
        encoding="utf-8",
    )

    try:
        uploader.load_queue(queue)
    except ValueError as exc:
        assert "approved issue queue failed quality validation" in str(exc)
    else:
        raise AssertionError("expected quality validation failure")


def test_upload_dry_run_skips_exact_title_duplicates(monkeypatch) -> None:
    def fake_fetch_open_issues(repo: str, prefix: list[str]):
        assert repo == "owner/repo"
        assert prefix == ["gh"]
        return [
            {
                "number": 5,
                "title": "Existing issue",
                "url": "https://github.test/owner/repo/issues/5",
                "labels": [],
            }
        ]

    monkeypatch.setattr(uploader, "fetch_open_issues", fake_fetch_open_issues)
    issues = [
        {"repo": "owner/repo", "title": "Existing issue", "labels": [], "body": VALID_BODY},
        {"repo": "owner/repo", "title": "New issue", "labels": [], "body": VALID_BODY},
    ]

    summary = uploader.upload_issues(issues, prefix=["gh"], apply=False)

    assert summary["skipped_duplicates"] == [
        {
            "repo": "owner/repo",
            "title": "Existing issue",
            "number": 5,
            "url": "https://github.test/owner/repo/issues/5",
        }
    ]
    assert summary["would_create"] == [{"repo": "owner/repo", "title": "New issue"}]
