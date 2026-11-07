"""Link one FULL consumer regeneration through qualification, promotion, and reconciliation.

The recorded chain is the Maint 68/71 full plan whose source commit already contains
the merged #3900 dependency. Branch-cleanup retries stay visible and do not count
as a failed delivery reconciliation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_SHA_CHARS = frozenset("0123456789abcdef")
_PLAN_PREFIX = "sha256:"
_STAGES = ("qualification", "promotion", "reconciliation")

# Observed 2026-11-06. Source 306fc9e7 contains merge 8ec052a1 (#3900).
# Qualification 41128486728 dispatched promotion 41128622575, which started
# reconciliation 41128913051. Continuation 41132061438 authorized that plan
# and merged the fleet heads below.
FULL_CONSUMER_REGENERATION_3900: dict[str, object] = {
    "plan_id": "sha256:1a22f551228736c4279b2b5434baffbb0e6d5b697dc43727bf5d7f808209dc0b",
    "plan_scope": "full",
    "source_commit": "306fc9e79d891030395211fdae8ae1387f2b37c3",
    "dependency": {
        "pull_request": 3900,
        "merge_commit": "8ec052a1fdc32319165011a7e465d6710c7ef4b5",
        "merged_at": "2026-10-15T01:32:54Z",
        "url": "https://github.com/stranske/Workflows/pull/3900",
    },
    "commands": (
        "gh pr view 3900 --repo stranske/Workflows --json state,mergedAt,mergeCommit",
        "git merge-base --is-ancestor 8ec052a1fdc32319165011a7e465d6710c7ef4b5 "
        "306fc9e79d891030395211fdae8ae1387f2b37c3",
        "gh run view 41128486728 --repo stranske/Workflows",
        "gh run view 41128622575 --repo stranske/Workflows",
        "gh run view 41132061438 --repo stranske/Workflows",
    ),
    "qualification": {
        "run_id": 41128486728,
        "conclusion": "success",
        "workflow": "maint-71-merge-sync-prs.yml",
        "url": "https://github.com/stranske/Workflows/actions/runs/41128486728",
        "canaries_green": 3,
        "canaries_expected": 3,
        "notice": (
            "promote: blocked none; canaries green 3/3; drainable 3; "
            "Canary promotion sha256:1a22f551228736c4279b2b5434baffbb0e6d5b697dc43727bf5d7f808209dc0b: "
            "dispatched; source 306fc9e79d891030395211fdae8ae1387f2b37c3; "
            "completion awaits a successful Maint 68 run"
        ),
        "heads": (
            {
                "repository": "stranske/Travel-Plan-Permission",
                "pr": 1715,
                "head_sha": "80ae115d052d8668e048d4d3f30b1feaf0e3be09",
            },
            {
                "repository": "stranske/trip-planner",
                "pr": 1954,
                "head_sha": "b900b51f7f4488dd222736686a0d5c720c7c9148",
            },
            {
                "repository": "stranske/Portable-Alpha-Extension-Model",
                "pr": 2452,
                "head_sha": "eee634cd09e283e218e4670d15bba62de61bcde8",
            },
        ),
    },
    "promotion": {
        "run_id": 41128622575,
        "conclusion": "success",
        "phase": "promote",
        "workflow": "maint-68-sync-consumer-repos.yml",
        "url": "https://github.com/stranske/Workflows/actions/runs/41128622575",
        "reconciliation_run_id": 41128913051,
    },
    "reconciliation": {
        "run_id": 41132061438,
        "conclusion": "success",
        "workflow": "maint-71-merge-sync-prs.yml",
        "url": "https://github.com/stranske/Workflows/actions/runs/41132061438",
        "authorized": True,
        "merged": 16,
        "failed": 0,
        "pending": 0,
        "continuation_run_ids": (41128913051, 41130701739, 41132061438),
        "branch_cleanup_notice": (
            "13 sync branch(es) could not be deleted; the next scheduled run retries the cleanup."
        ),
        # Run 41132061438 authorized and merged this plan. The live notice also
        # listed missing canary evidence because empty refresh evidence was
        # validated. That is not a canary hold: there was no refresh request.
        "delivery_refresh": {
            "eligible": False,
            "errors": ("delivery report has no stable base refresh request",),
        },
        "heads": (
            {
                "repository": "stranske/Travel-Plan-Permission",
                "pr": 1715,
                "head_sha": "80ae115d052d8668e048d4d3f30b1feaf0e3be09",
            },
            {
                "repository": "stranske/Template",
                "pr": 1097,
                "head_sha": "3fc4565e95f38d3867d1b7f4759ca961e7a795c2",
            },
            {
                "repository": "stranske/Counter_Risk",
                "pr": 1224,
                "head_sha": "7058ca246d94b740785c252835c7ab6237bcb421",
            },
            {
                "repository": "stranske/Pension-Data",
                "pr": 1007,
                "head_sha": "88d98c77481ff012db1dc38b94b11150c7d4a3ac",
            },
            {
                "repository": "stranske/Inv-Man-Intake",
                "pr": 1060,
                "head_sha": "333b9dea43bbf91cea1c6f334ced4b66332662ef",
            },
            {
                "repository": "stranske/Ready",
                "pr": 661,
                "head_sha": "94a6f8f929e87b5d9a9714911bb245dc3b59d384",
            },
            {
                "repository": "stranske/trip-planner",
                "pr": 1954,
                "head_sha": "b900b51f7f4488dd222736686a0d5c720c7c9148",
            },
            {
                "repository": "stranske/Manager-Database",
                "pr": 1872,
                "head_sha": "2bbb88acefe8961eef3a091ba3d084cac1e05084",
            },
            {
                "repository": "stranske/Portable-Alpha-Extension-Model",
                "pr": 2452,
                "head_sha": "eee634cd09e283e218e4670d15bba62de61bcde8",
            },
            {
                "repository": "stranske/Trend_Model_Project",
                "pr": 6180,
                "head_sha": "ec2b575cd9379425db8096b57f3835aa2466b8c0",
            },
            {
                "repository": "stranske/learning-management-system",
                "pr": 814,
                "head_sha": "ef2406e8b0c348ba7cdcd5ba080e354cca1bfcb7",
            },
            {
                "repository": "stranske/Fine-Art-Archive",
                "pr": 865,
                "head_sha": "2747012a4d3c0730d9ce09b468a2ebdbd88db992",
            },
            {
                "repository": "stranske/Orchestrator",
                "pr": 1016,
                "head_sha": "29aaf359c9d81b2b4a0a8f50d4c0e65fe2ce5b14",
            },
            {
                "repository": "stranske/Doc-Lineage",
                "pr": 166,
                "head_sha": "3e42ab7243eadd39322697b8251e478681b1a450",
            },
            {
                "repository": "stranske/Deliverable-Render",
                "pr": 125,
                "head_sha": "a4d2026d88aaad5762b970643c27187f0202206b",
            },
            {
                "repository": "stranske/Manager-Mosaic",
                "pr": 141,
                "head_sha": "ae747511212875ddb0007e3cc343c48bbae228bb",
            },
        ),
    },
}


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


def regeneration_gaps(record: Mapping[str, object]) -> tuple[str, ...]:
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
