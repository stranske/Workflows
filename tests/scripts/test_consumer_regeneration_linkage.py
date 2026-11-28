"""FULL consumer regeneration stays tied to one plan, its heads, and merged #3900.

The delivery had no refresh request. Run 41132061438 authorized and merged the plan.
Its live notice reported missing canary evidence because it validated an empty refresh.
The branch-cleanup retry did not change the delivery outcome.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SOURCE = "306fc9e79d891030395211fdae8ae1387f2b37c3"
DEPENDENCY = "8ec052a1fdc32319165011a7e465d6710c7ef4b5"
PLAN = "sha256:1a22f551228736c4279b2b5434baffbb0e6d5b697dc43727bf5d7f808209dc0b"


_SHA_CHARS = frozenset("0123456789abcdef")
_PLAN_PREFIX = "sha256:"
_STAGES = ("qualification", "promotion", "reconciliation")


def _sha(value: object) -> str | None:
    if isinstance(value, str) and len(value) == 40 and set(value) <= _SHA_CHARS:
        return value
    return None


def _plan_id(value: object) -> str | None:
    if (
        isinstance(value, str)
        and value.startswith(_PLAN_PREFIX)
        and len(value) == len(_PLAN_PREFIX) + 64
        and set(value.removeprefix(_PLAN_PREFIX)) <= _SHA_CHARS
    ):
        return value
    return None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _https(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _exact_int(value: object, expected: int) -> bool:
    """True only for that integer. False and 0.0 compare equal to 0 and are refused."""
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _run_id(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _head_identity(head: Mapping[str, object]) -> tuple[str, int, str] | None:
    repository = head.get("repository")
    pull_request = head.get("pr")
    head_sha = _sha(head.get("head_sha"))
    if (
        not _text(repository)
        or not isinstance(pull_request, int)
        or isinstance(pull_request, bool)
        or pull_request <= 0
        or head_sha is None
    ):
        return None
    return (str(repository), pull_request, head_sha)


def _head_gaps(heads: object, prefix: str) -> tuple[str, ...]:
    if not isinstance(heads, Sequence) or isinstance(heads, (str, bytes)) or not heads:
        return (f"{prefix}.heads",)
    gaps: list[str] = []
    seen: set[str] = set()
    for index, head in enumerate(heads):
        label = f"{prefix}.heads[{index}]"
        if not isinstance(head, Mapping) or _head_identity(head) is None:
            gaps.append(label)
            continue
        repository = str(head.get("repository"))
        if repository in seen:
            gaps.append(f"{label}.repository")
        seen.add(repository)
    return tuple(gaps)


def _command_gaps(commands: object, record: Mapping[str, object]) -> tuple[str, ...]:
    if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes)) or not commands:
        return ("commands",)
    rendered = "\n".join(command for command in commands if isinstance(command, str))
    required = [record.get("source_commit")]
    dependency = record.get("dependency")
    if isinstance(dependency, Mapping):
        required.append(dependency.get("merge_commit"))
    for stage in ("qualification", "promotion", "reconciliation"):
        body = record.get(stage)
        if isinstance(body, Mapping):
            required.append(body.get("run_id"))
    gaps: list[str] = []
    for index, command in enumerate(commands):
        if not _text(command):
            gaps.append(f"commands[{index}]")
    for value in required:
        if value is None or str(value) not in rendered:
            gaps.append("commands.binding")
            break
    return tuple(gaps)


def _regeneration_gaps(record: Mapping[str, object]) -> tuple[str, ...]:
    """Return why qualification, promotion, and reconciliation are not one full plan."""
    if not isinstance(record, Mapping):
        return ("record",)
    gaps: list[str] = []
    plan_id = _plan_id(record.get("plan_id"))
    source = _sha(record.get("source_commit"))
    if plan_id is None:
        gaps.append("plan_id")
    if record.get("plan_scope") != "full":
        gaps.append("plan_scope")
    if source is None:
        gaps.append("source_commit")

    dependency = record.get("dependency")
    if not isinstance(dependency, Mapping):
        gaps.append("dependency")
    else:
        pull_request = dependency.get("pull_request")
        merge_commit = _sha(dependency.get("merge_commit"))
        if (
            not isinstance(pull_request, int)
            or isinstance(pull_request, bool)
            or pull_request <= 0
            or merge_commit is None
            or merge_commit == source
            or not _text(dependency.get("merged_at"))
            or not _https(dependency.get("url"))
        ):
            gaps.append("dependency")

    gaps.extend(_command_gaps(record.get("commands"), record))
    for stage in _STAGES:
        if not isinstance(record.get(stage), Mapping):
            gaps.append(stage)

    qualification = record.get("qualification")
    promotion = record.get("promotion")
    reconciliation = record.get("reconciliation")
    qualified: dict[str, tuple[int, str]] = {}
    if isinstance(qualification, Mapping):
        green = qualification.get("canaries_green")
        expected = qualification.get("canaries_expected")
        if (
            not _run_id(qualification.get("run_id"))
            or qualification.get("conclusion") != "success"
            or not _https(qualification.get("url"))
            or not _text(qualification.get("notice"))
            or green != expected
            or not _count(expected)
            or expected == 0
        ):
            gaps.append("qualification.verdict")
        gaps.extend(_head_gaps(qualification.get("heads"), "qualification"))
        heads = qualification.get("heads")
        if isinstance(heads, Sequence) and not isinstance(heads, (str, bytes)):
            if _count(expected) and len(heads) != expected:
                gaps.append("qualification.heads")
            for head in heads:
                if not isinstance(head, Mapping):
                    continue
                identity = _head_identity(head)
                if identity is None:
                    continue
                qualified[identity[0]] = (identity[1], identity[2])

    promotion_run = None
    if isinstance(promotion, Mapping):
        promotion_run = promotion.get("run_id")
        if (
            not _run_id(promotion_run)
            or promotion.get("conclusion") != "success"
            or promotion.get("phase") != "promote"
            or not _https(promotion.get("url"))
            or not _run_id(promotion.get("reconciliation_run_id"))
        ):
            gaps.append("promotion.verdict")

    if isinstance(reconciliation, Mapping):
        merged = reconciliation.get("merged")
        heads = reconciliation.get("heads")
        continuation = reconciliation.get("continuation_run_ids")
        head_count = (
            len(heads)
            if isinstance(heads, Sequence) and not isinstance(heads, (str, bytes))
            else -1
        )
        if (
            not _run_id(reconciliation.get("run_id"))
            or reconciliation.get("conclusion") != "success"
            or reconciliation.get("authorized") is not True
            or not _exact_int(reconciliation.get("failed"), 0)
            or not _exact_int(reconciliation.get("pending"), 0)
            or not _count(merged)
            or merged != head_count
            or not _https(reconciliation.get("url"))
            or not _text(reconciliation.get("branch_cleanup_notice"))
        ):
            gaps.append("reconciliation.verdict")
        refresh = reconciliation.get("delivery_refresh")
        refresh_errors = refresh.get("errors") if isinstance(refresh, Mapping) else None
        rendered = (
            tuple(refresh_errors)
            if isinstance(refresh_errors, Sequence)
            and not isinstance(refresh_errors, (str, bytes))
            and all(_text(item) for item in refresh_errors)
            else None
        )
        no_refresh = rendered == ("delivery report has no stable base refresh request",)
        completed_refresh = rendered == ()
        false_canary_hold = rendered is not None and any(
            "missing_canary_evidence" in item or "missing_or_mixed_canary_plan" in item
            for item in rendered
        )
        eligible = refresh.get("eligible") if isinstance(refresh, Mapping) else None
        if (
            rendered is None
            or false_canary_hold
            or not isinstance(eligible, bool)
            or (eligible is False and not no_refresh)
            or (eligible is True and not completed_refresh)
        ):
            gaps.append("reconciliation.delivery_refresh")
        gaps.extend(_head_gaps(heads, "reconciliation"))
        if not isinstance(continuation, Sequence) or isinstance(continuation, (str, bytes)):
            gaps.append("reconciliation.continuation")
        else:
            run_ids = [value for value in continuation if _run_id(value)]
            if (
                len(run_ids) != len(tuple(continuation))
                or not run_ids
                or run_ids[-1] != reconciliation.get("run_id")
                or (
                    isinstance(promotion, Mapping)
                    and run_ids[0] != promotion.get("reconciliation_run_id")
                )
            ):
                gaps.append("reconciliation.continuation")
        if isinstance(heads, Sequence) and not isinstance(heads, (str, bytes)):
            delivered = {}
            for head in heads:
                if isinstance(head, Mapping):
                    identity = _head_identity(head)
                    if identity is not None:
                        delivered[identity[0]] = (identity[1], identity[2])
            if qualified and any(item not in delivered.items() for item in qualified.items()):
                gaps.append("reconciliation.qualified_heads")
        if (
            _run_id(promotion_run)
            and _run_id(reconciliation.get("run_id"))
            and promotion_run == reconciliation.get("run_id")
        ):
            gaps.append("reconciliation.run_id")

    if (
        isinstance(qualification, Mapping)
        and isinstance(promotion, Mapping)
        and _run_id(qualification.get("run_id"))
        and qualification.get("run_id") == promotion.get("run_id")
    ):
        gaps.append("promotion.run_id")
    return tuple(gaps)


# Observed 2026-11-06. Source 306fc9e7 contains merge 8ec052a1 (#3900).
# Qualification 41128486728 dispatched promotion 41128622575, which started
# reconciliation 41128913051. Continuation 41132061438 authorized that plan
# and merged the fleet heads below.
def _record() -> dict:
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/issue_3901/full_consumer_regeneration_3900.json"
    )
    return json.loads(fixture.read_text(encoding="utf-8"))


def test_full_regeneration_links_qualification_promotion_and_reconciliation() -> None:
    record = _record()
    assert _regeneration_gaps(record) == ()
    assert record["plan_id"] == PLAN
    assert record["plan_scope"] == "full"
    assert record["source_commit"] == SOURCE
    assert record["dependency"]["pull_request"] == 3900
    assert record["dependency"]["merge_commit"] == DEPENDENCY
    assert record["qualification"]["canaries_green"] == 3
    assert record["promotion"]["phase"] == "promote"
    assert record["promotion"]["reconciliation_run_id"] == 41128913051
    assert record["reconciliation"]["authorized"] is True
    assert record["reconciliation"]["merged"] == 16
    assert record["reconciliation"]["failed"] == 0
    assert record["reconciliation"]["pending"] == 0
    assert record["reconciliation"]["delivery_refresh"]["eligible"] is False
    assert tuple(record["reconciliation"]["delivery_refresh"]["errors"]) == (
        "delivery report has no stable base refresh request",
    )
    assert "306fc9e79d891030395211fdae8ae1387f2b37c3" in record["qualification"]["notice"]
    assert "canaries green 3/3" in record["qualification"]["notice"]
    assert (
        record["reconciliation"]["continuation_run_ids"][-1] == record["reconciliation"]["run_id"]
    )
    qualified = {
        (head["repository"], head["pr"], head["head_sha"])
        for head in record["qualification"]["heads"]
    }
    delivered = {
        (head["repository"], head["pr"], head["head_sha"])
        for head in record["reconciliation"]["heads"]
    }
    assert qualified <= delivered
    assert len(delivered) == 16


def _commit_present(sha: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def test_source_commit_contains_merged_3900() -> None:
    # Required Python CI fetches the fixed historical source before pytest.
    # Ad hoc shallow checkouts may skip; required validation must fail closed.
    if not _commit_present(DEPENDENCY) or not _commit_present(SOURCE):
        if os.environ.get("WORKFLOWS_REQUIRE_3900_ANCESTRY") == "1":
            pytest.fail("required dependency and source history is absent")
        pytest.skip("dependency and source commits are absent from this checkout")
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", DEPENDENCY, SOURCE],
        cwd=REPO,
        check=False,
    )
    assert completed.returncode == 0


def test_commands_name_the_plan_source_dependency_and_runs() -> None:
    record = _record()
    rendered = "\n".join(record["commands"])
    assert record["plan_id"] == PLAN
    assert SOURCE in rendered
    assert DEPENDENCY in rendered
    for run_id in (41128486728, 41128622575, 41132061438):
        assert str(run_id) in rendered


def test_required_ancestry_cannot_skip_missing_history(monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOWS_REQUIRE_3900_ANCESTRY", "1")
    monkeypatch.setattr(f"{__name__}._commit_present", lambda _sha: False)
    with pytest.raises(pytest.fail.Exception, match="required dependency and source history"):
        test_source_commit_contains_merged_3900()


def test_missing_stage_is_unlinked() -> None:
    for stage in ("qualification", "promotion", "reconciliation"):
        record = _record()
        del record[stage]
        assert stage in _regeneration_gaps(record)


def test_non_mapping_stage_is_unlinked() -> None:
    for stage in ("qualification", "promotion", "reconciliation"):
        record = _record()
        record[stage] = "success"
        assert stage in _regeneration_gaps(record)


def test_boolean_and_float_zero_are_not_terminal_counts() -> None:
    for field, value in (
        ("failed", False),
        ("pending", False),
        ("failed", 0.0),
        ("pending", 0.0),
    ):
        record = _record()
        record["reconciliation"][field] = value
        assert "reconciliation.verdict" in _regeneration_gaps(record)


def test_integer_eligibility_with_another_refresh_error_is_not_terminal() -> None:
    record = _record()
    record["reconciliation"]["delivery_refresh"] = {
        "eligible": 0,
        "errors": ("writer exited before authorization",),
    }
    assert "reconciliation.delivery_refresh" in _regeneration_gaps(record)


def test_failed_reconciliation_is_unlinked() -> None:
    record = _record()
    record["reconciliation"]["failed"] = 1
    assert "reconciliation.verdict" in _regeneration_gaps(record)


def test_qualified_head_must_survive_reconciliation() -> None:
    record = _record()
    record["qualification"]["heads"][0]["head_sha"] = "a" * 40
    assert "reconciliation.qualified_heads" in _regeneration_gaps(record)


def test_source_delta_scope_is_not_a_full_regeneration() -> None:
    record = _record()
    record["plan_scope"] = "source-delta"
    assert "plan_scope" in _regeneration_gaps(record)


def test_false_canary_hold_is_not_terminal_reconciliation() -> None:
    record = _record()
    record["reconciliation"]["delivery_refresh"]["errors"] = (
        "delivery report has no stable base refresh request",
        "missing_canary_evidence:stranske/Travel-Plan-Permission",
        "missing_or_mixed_canary_plan",
    )
    assert "reconciliation.delivery_refresh" in _regeneration_gaps(record)


def test_dependency_merge_cannot_be_the_plan_source() -> None:
    record = _record()
    record["dependency"]["merge_commit"] = SOURCE
    assert "dependency" in _regeneration_gaps(record)
