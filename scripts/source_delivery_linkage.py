"""Link exact-head review, CI, guarded merge, and durable disposition for one source head.

Workflow success is not a provider verdict. A durable NON_PASS disposition stays
NON_PASS when the Actions run that published it completed successfully.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_SHA_CHARS = frozenset("0123456789abcdef")
_CHANNELS = (
    "exact_head_review",
    "actual_ci",
    "guarded_merge",
    "durable_disposition",
)
_AUTO_MERGE_JOBS = frozenset({"success", "skipped", "failure"})
_DISPOSITIONS = frozenset({"PASS", "NON_PASS", "CONCERNS"})

# Delivered report-family source change. Inspected 2026-11-06 from PR #3902.
# The orchestrator auto-merge job was skipped; GitHub records an owner merge
# after the exact-head topology gates. Provider comparison stayed NON_PASS.
REPORT_FAMILY_DELIVERY_3902: dict[str, object] = {
    "pull_request": 3902,
    "repository": "stranske/Workflows",
    "head_sha": "86a036ee03344e1d660fc7528bb21b06e7bea642",
    "exact_head_review": {
        "commit_sha": "86a036ee03344e1d660fc7528bb21b06e7bea642",
        "reviewer": "chatgpt-codex-connector[bot]",
        "state": "COMMENTED",
        "submitted_at": "2026-10-14T18:08:46Z",
        "url": "https://github.com/stranske/Workflows/pull/3902#pullrequestreview-5522442968",
    },
    "actual_ci": (
        {
            "name": "Gate",
            "run_id": 38609812734,
            "conclusion": "success",
            "head_sha": "86a036ee03344e1d660fc7528bb21b06e7bea642",
            "url": "https://github.com/stranske/Workflows/actions/runs/38609812734",
        },
        {
            "name": "Selftest CI",
            "run_id": 38609812639,
            "conclusion": "success",
            "head_sha": "86a036ee03344e1d660fc7528bb21b06e7bea642",
            "url": "https://github.com/stranske/Workflows/actions/runs/38609812639",
        },
    ),
    "guarded_merge": {
        "merge_commit": "5d0a45e49297b13968e402020a8b26284bd1907b",
        "actor": "stranske",
        "merged_at": "2026-10-14T18:52:48Z",
        "url": "https://github.com/stranske/Workflows/pull/3902",
        "orchestrator_run_id": 38617875945,
        "auto_merge_job": "skipped",
    },
    "durable_disposition": {
        "run_id": 38618948337,
        "workflow_conclusion": "success",
        "provider_verdict": "CONCERNS",
        "disposition": "NON_PASS",
        "head_sha": "86a036ee03344e1d660fc7528bb21b06e7bea642",
        "run_url": "https://github.com/stranske/Workflows/actions/runs/38618948337",
        "comparison_url": "https://github.com/stranske/Workflows/pull/3902#issuecomment-6176051552",
        "issue_comment_url": "https://github.com/stranske/Workflows/issues/3901#issuecomment-6176277111",
    },
}


def _sha(value: object) -> str | None:
    if isinstance(value, str) and len(value) == 40 and set(value) <= _SHA_CHARS:
        return value
    return None


def _https(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _review_gaps(review: object, head: str | None) -> tuple[str, ...]:
    if not isinstance(review, Mapping):
        return ("exact_head_review",)
    gaps: list[str] = []
    commit = _sha(review.get("commit_sha"))
    if commit is None or (head is not None and commit != head):
        gaps.append("exact_head_review.commit_sha")
    if not _text(review.get("reviewer")) or not _text(review.get("state")):
        gaps.append("exact_head_review.identity")
    if not _text(review.get("submitted_at")) or not _https(review.get("url")):
        gaps.append("exact_head_review.url")
    return tuple(gaps)


def _ci_gaps(runs: object, head: str | None) -> tuple[str, ...]:
    if not isinstance(runs, Sequence) or isinstance(runs, (str, bytes)) or not runs:
        return ("actual_ci",)
    gaps: list[str] = []
    for index, run in enumerate(runs):
        prefix = f"actual_ci[{index}]"
        if not isinstance(run, Mapping):
            gaps.append(prefix)
            continue
        run_head = _sha(run.get("head_sha"))
        run_id = run.get("run_id")
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
            gaps.append(f"{prefix}.run_id")
        if run.get("conclusion") != "success" or run_head is None or (head and run_head != head):
            gaps.append(f"{prefix}.head")
        if not _text(run.get("name")) or not _https(run.get("url")):
            gaps.append(f"{prefix}.url")
    return tuple(gaps)


def _merge_gaps(merge: object, head: str | None) -> tuple[str, ...]:
    if not isinstance(merge, Mapping):
        return ("guarded_merge",)
    gaps: list[str] = []
    merge_commit = _sha(merge.get("merge_commit"))
    if merge_commit is None or (head is not None and merge_commit == head):
        gaps.append("guarded_merge.merge_commit")
    if (
        not _text(merge.get("actor"))
        or not _text(merge.get("merged_at"))
        or not _https(merge.get("url"))
    ):
        gaps.append("guarded_merge.identity")
    run_id = merge.get("orchestrator_run_id")
    if (
        not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or run_id <= 0
        or merge.get("auto_merge_job") not in _AUTO_MERGE_JOBS
    ):
        gaps.append("guarded_merge.auto_merge_job")
    return tuple(gaps)


def _disposition_gaps(disposition: object, head: str | None) -> tuple[str, ...]:
    if not isinstance(disposition, Mapping):
        return ("durable_disposition",)
    gaps: list[str] = []
    run_id = disposition.get("run_id")
    recorded = disposition.get("disposition")
    provider = disposition.get("provider_verdict")
    bound_head = _sha(disposition.get("head_sha"))
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        gaps.append("durable_disposition.run_id")
    if disposition.get("workflow_conclusion") not in {"success", "failure"}:
        gaps.append("durable_disposition.workflow_conclusion")
    if recorded not in _DISPOSITIONS or not _text(provider):
        gaps.append("durable_disposition.verdict")
    elif recorded == "PASS" and provider != "PASS":
        gaps.append("durable_disposition.overrides_provider")
    if bound_head is None or (head is not None and bound_head != head):
        gaps.append("durable_disposition.head_sha")
    if not _https(disposition.get("run_url")) or not _https(disposition.get("comparison_url")):
        gaps.append("durable_disposition.url")
    return tuple(gaps)


def linkage_gaps(record: Mapping[str, object]) -> tuple[str, ...]:
    """Return why review, CI, merge, and disposition are not one exact-head delivery."""
    if not isinstance(record, Mapping):
        return ("record",)
    gaps: list[str] = []
    pull_request = record.get("pull_request")
    if not isinstance(pull_request, int) or isinstance(pull_request, bool) or pull_request <= 0:
        gaps.append("pull_request")
    if not _text(record.get("repository")):
        gaps.append("repository")
    head = _sha(record.get("head_sha"))
    if head is None:
        gaps.append("head_sha")
    for channel in _CHANNELS:
        if channel not in record:
            gaps.append(channel)
    if "exact_head_review" in record:
        gaps.extend(_review_gaps(record.get("exact_head_review"), head))
    if "actual_ci" in record:
        gaps.extend(_ci_gaps(record.get("actual_ci"), head))
    if "guarded_merge" in record:
        gaps.extend(_merge_gaps(record.get("guarded_merge"), head))
    if "durable_disposition" in record:
        gaps.extend(_disposition_gaps(record.get("durable_disposition"), head))
    return tuple(gaps)
