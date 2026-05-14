"""Static guard: every workflow YAML file uses only real GitHub Actions
triggers in its top-level ``on:`` block.

Background — why this test exists
=================================
PR #1528 (merged 2026-02-16) added::

    on:
      workflow_job:
        types: [completed]

…to the consumer-repo autofix.yml template. ``workflow_job`` is a *webhook
event* (delivered to org-level webhook subscribers); it is **not** a valid
``on:`` trigger for a GitHub Actions workflow. Every push to every consumer
repo since the 2026-02-17 sync has recorded a failed Autofix run with the
opaque message "This run likely failed because of a workflow file issue."
The failure mode wasn't load-bearing — the working `workflow_run` path on
the same workflow continued to fire — so it took ~3 months to detect.

Two reasons CI didn't catch the regression at PR time:

1. The workflow only runs via the triggers listed in its ``on:`` block. The
   PR itself didn't fire any of those triggers, so the workflow was never
   instantiated during PR CI, and the "This run likely failed" recording
   was visible only after merge + sync.
2. The same PR added an ``actionlint-allowlist.txt`` entry for
   ``unknown Webhook event "workflow_job"`` — the static check that would
   have flagged the unknown event was explicitly silenced.

This test is a belt-and-suspenders companion to actionlint. It enumerates
every ``.github/workflows/*.yml`` and every ``templates/**/.github/
workflows/*.yml`` in the repo, parses the YAML, and asserts every
top-level ``on:`` key is in the documented set of workflow trigger events.
Unknown trigger names fail the test loudly, naming the file and the bad
event, so a future "feat: trigger early on $not_a_real_event" PR cannot
make it through review by hiding behind an allowlist tweak.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

# Source: https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows
# Keep alphabetized. ``workflow_job`` deliberately omitted — it's a webhook
# event for webhook subscribers, NOT a workflow trigger.
VALID_WORKFLOW_TRIGGERS: frozenset[str] = frozenset(
    {
        "branch_protection_rule",
        "check_run",
        "check_suite",
        "create",
        "delete",
        "deployment",
        "deployment_status",
        "discussion",
        "discussion_comment",
        "fork",
        "gollum",
        "issue_comment",
        "issues",
        "label",
        "merge_group",
        "milestone",
        "page_build",
        "project",
        "project_card",
        "project_column",
        "public",
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
        "pull_request_target",
        "push",
        "registry_package",
        "release",
        "repository_dispatch",
        "schedule",
        "status",
        "watch",
        "workflow_call",
        "workflow_dispatch",
        "workflow_run",
    }
)

WORKFLOW_GLOBS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "templates/**/.github/workflows/*.yml",
    "templates/**/.github/workflows/*.yaml",
)


def _iter_workflow_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in WORKFLOW_GLOBS:
        for path in ROOT.glob(pattern):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def _load_workflow(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - YAML linter handles this
        pytest.fail(f"{path.relative_to(ROOT)}: YAML parse error: {exc}")
    if not isinstance(data, dict):
        pytest.fail(f"{path.relative_to(ROOT)}: top-level YAML is not a mapping")
    return data


def _extract_on_events(on_field: object) -> list[str]:
    """Return the set of trigger event names referenced in the ``on:`` field.

    ``on:`` can be a string (``on: push``), a list (``on: [push, pull_request]``),
    or a mapping (``on: { push: { branches: [main] } }``). Handle all three.
    """
    if isinstance(on_field, str):
        return [on_field]
    if isinstance(on_field, list):
        return [str(item) for item in on_field if isinstance(item, str)]
    if isinstance(on_field, dict):
        return list(on_field.keys())
    return []


def test_at_least_one_workflow_file_is_discovered() -> None:
    """Guard against the glob silently matching nothing — that would let
    every other assertion below trivially pass."""
    files = list(_iter_workflow_files())
    assert files, (
        f"No workflow YAML files found under {ROOT} — the glob patterns "
        f"{WORKFLOW_GLOBS} matched nothing, so this test would trivially pass."
    )


@pytest.mark.parametrize(
    "workflow_path", list(_iter_workflow_files()), ids=lambda p: str(p.relative_to(ROOT))
)
def test_workflow_only_uses_valid_on_triggers(workflow_path: Path) -> None:
    """Every event listed under ``on:`` must be a real workflow trigger.

    A failure here means a workflow was authored with an event name that
    GitHub Actions does not recognize as a trigger. The most likely cause
    is a typo (``pull_resquest_target``), a confusion with a webhook event
    (``workflow_job`` — the canonical example this test was written to
    catch, see PR #1528 and 2026-05-14 incident notes), or a draft for an
    event that doesn't exist.
    """
    data = _load_workflow(workflow_path)
    on_field = data.get("on") if isinstance(data, dict) else None
    # `on` is a YAML reserved word coerced to Python True if not quoted.
    # PyYAML safe_load handles `on: <event>` by binding the key True — handle
    # that too so we still inspect the events.
    if on_field is None and True in data:
        on_field = data[True]

    events = _extract_on_events(on_field)
    assert events, (
        f"{workflow_path.relative_to(ROOT)}: could not parse `on:` block "
        f"(field={on_field!r}); a workflow without triggers will never run."
    )

    invalid = [event for event in events if event not in VALID_WORKFLOW_TRIGGERS]
    assert not invalid, (
        f"{workflow_path.relative_to(ROOT)}: uses unknown `on:` event(s) "
        f"{invalid}. Allowed events are documented at "
        "https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows. "
        "If you intend to react to a webhook event delivered to a repo "
        "subscription, you cannot do so directly — webhook events are NOT "
        "valid workflow triggers. Consider `workflow_run` (for workflow "
        "completion) or `check_run`/`check_suite` (for CI lifecycle) instead."
    )
