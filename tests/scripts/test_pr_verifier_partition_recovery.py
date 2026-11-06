"""Bounded diagnostic partitions never upgrade globally dependent obligations."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest import mock

import pytest
from scripts.langchain import pr_verifier

from tests.scripts.test_native_capacity_recovery import native as _native_fixture
from tests.scripts.verifier_capacity_fakes import complete_capture_context

native = _native_fixture


@pytest.fixture
def recovery(native, monkeypatch):
    client, provider, model, counter, _ = native
    monkeypatch.setenv("VERIFIER_PARTITION_RECOVERY", "diagnostic")
    monkeypatch.setenv("VERIFIER_CONTEXT_BUDGET_TOKENS", "100000")
    original = pr_verifier._native_capacity_contract

    def contract(prepared):
        value = original(prepared)
        value["profile"]["max_input_tokens"] = 12000
        value["profile"]["max_context_tokens"] = 140000
        return value

    monkeypatch.setattr(pr_verifier, "_native_capacity_contract", contract)
    key = "input" if provider == "openai" else "messages"
    counter.side_effect = lambda **kwargs: SimpleNamespace(
        input_tokens=len(json.dumps(kwargs[key], ensure_ascii=False))
    )
    context = complete_capture_context().replace(
        "No failures.", "No failures.\r\n" + ("evidence café 🧪\n" * 2000)
    )
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, provider))
    return client, provider, model, counter, context


def _run(recovery, operation):
    client, provider, model, _, context = recovery
    if operation == "compare":
        return pr_verifier.ComparisonRunner(
            context, None, pr_verifier._prepare_prompt(context, None), []
        ).run_single(client, provider, model)
    return pr_verifier.evaluate_pr(context, provider=provider)


@pytest.mark.parametrize("operation", ["evaluate", "compare"])
def test_partition_recovery_preflights_all_ranges_and_retains_every_finding(recovery, operation):
    client, _, _, counter, context = recovery
    generated = []

    def generate(prepared, prompt, **kwargs):
        # Every planned range was already counted before the first generation.
        if not generated:
            assert counter.call_count > 2
        generated.append(prompt)
        return SimpleNamespace(
            content=json.dumps(
                {
                    "verdict": "PASS",
                    "concerns": [f"finding-{len(generated)}"],
                    "summary": f"gap-{len(generated)}",
                }
            )
        )

    with mock.patch.object(type(client), "invoke", autospec=True, side_effect=generate):
        result = _run(recovery, operation)
    assert len(generated) > 1
    assert result.verdict == "CONCERNS" and result.used_llm
    report = result.partition_recovery
    assert report["status"] == "diagnostic_complete"
    assert report["acceptance_sufficient"] is False
    assert report["contract"]["dependency_policy"] == "all-captured-inputs"
    assert report["binding_scope"] == "loaded-evaluation-inputs"
    assert len(report["results"]) == len(generated)
    reconstructed = "".join(prompt.split("\nCaptured range:\n", 1)[1] for prompt in generated)
    assert reconstructed == context
    assert hashlib.sha256(reconstructed.encode()).hexdigest() == report["inputs"][0]["sha256"]
    for index, row in enumerate(report["results"], 1):
        assert f"finding-{index}" in result.concerns
        assert f"gap-{index}" in result.summary
        assert row["raw_content"]
    assert report["ranges"][0]["start"] == 0
    assert report["ranges"][-1]["end"] == len(context)
    assert report["pending_ranges"] == []
    assert report["planning_preflights"] == len(report["planning_attempts"])
    assert report["planning_preflights"] <= pr_verifier.PARTITION_MAX_PLANNING_COUNTS
    assert any(row["capacity"]["status"] == "overflow" for row in report["planning_attempts"])
    for left, right in zip(report["ranges"], report["ranges"][1:], strict=False):
        assert left["end"] == right["start"]
    assert all(row["capacity"]["status"] == "PASS" for row in report["ranges"])
    assert len(generated) <= pr_verifier.PARTITION_MAX_REQUESTS
    for row in report["ranges"]:
        assert row["capacity"]["model"] == recovery[2]
        assert row["capacity"]["output_reserve"] == 128000
        assert row["capacity"]["input_tokens"] <= 12000


def test_partition_plan_includes_supplied_diff_without_losing_unicode_or_crlf(recovery):
    client, _, _, _, context = recovery
    diff = "diff --git a/a.py b/a.py\r\n" + ("+🧪 café\r\n" * 3000)
    with mock.patch.object(type(client), "invoke") as invoke:
        plan, prompts = pr_verifier._plan_diagnostic_partitions(client, context, diff)
    invoke.assert_not_called()
    recovered = {"context": "", "diff": ""}
    for row, prompt in zip(plan["ranges"], prompts, strict=True):
        recovered[row["input"]] += prompt.split("\nCaptured range:\n", 1)[1]
    assert recovered == {"context": context, "diff": diff}
    assert len(plan["contract"]["obligations"]) > 0


@pytest.mark.parametrize("defect", ["unavailable", "truncated", "count", "bound", "header"])
def test_partition_failure_blocks_all_generation(recovery, monkeypatch, defect):
    client, provider, _, counter, context = recovery
    if defect in {"unavailable", "truncated"}:
        context = context.replace('"status": "included"', f'"status": "{defect}"', 1)
    elif defect == "count":
        counter.side_effect = RuntimeError("count unavailable")
    elif defect == "bound":
        monkeypatch.setattr(pr_verifier, "PARTITION_MAX_REQUESTS", 1)
    else:
        counter.side_effect = lambda **kwargs: SimpleNamespace(input_tokens=12001)
    with mock.patch.object(type(client), "invoke") as invoke:
        result = pr_verifier.evaluate_pr(context, provider=provider)
    invoke.assert_not_called()
    assert result.verdict == "CONCERNS" and not result.used_llm
    assert result.error
    if defect in {"unavailable", "truncated", "count"}:
        assert result.partition_recovery is None
    else:
        assert result.partition_recovery["status"] == "blocked"
        assert counter.call_count <= 1 + 2 * pr_verifier.PARTITION_MAX_REQUESTS


@pytest.mark.parametrize("failure", ["transport", "malformed", "fail"])
def test_partition_failure_preserves_prior_findings_and_raw_outputs(recovery, failure):
    client, _, _, _, _ = recovery
    calls = []

    def generate(prepared, prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 2:
            if failure == "transport":
                raise RuntimeError("generation unavailable")
            if failure == "malformed":
                return SimpleNamespace(content="unparseable finding")
            return SimpleNamespace(content='{"verdict":"FAIL","concerns":["failure"]}')
        return SimpleNamespace(content='{"verdict":"PASS","concerns":["earlier finding"]}')

    with mock.patch.object(type(client), "invoke", autospec=True, side_effect=generate):
        result = _run(recovery, "evaluate")
    assert result.verdict == ("FAIL" if failure == "fail" else "CONCERNS")
    assert "earlier finding" in result.concerns
    assert result.partition_recovery["results"][0]["raw_content"]
    if failure != "fail":
        assert result.partition_recovery["status"] == "diagnostic_incomplete"
        assert result.error
    if failure == "malformed":
        assert "unparseable finding" in result.raw_content


def test_partition_recovery_is_explicit_and_expanded_only(recovery, monkeypatch):
    client, _, _, _, _ = recovery
    monkeypatch.delenv("VERIFIER_PARTITION_RECOVERY")
    with mock.patch.object(type(client), "invoke") as invoke:
        result = _run(recovery, "evaluate")
    invoke.assert_not_called()
    assert result.verdict == "CONCERNS" and result.partition_recovery is None


def test_partition_capture_bound_is_checked_before_any_count(recovery, monkeypatch):
    client, _, _, counter, context = recovery
    monkeypatch.setattr(pr_verifier, "PARTITION_MAX_CAPTURE_BYTES", 10)
    with pytest.raises(pr_verifier.InputCapacityError, match="capture byte"):
        pr_verifier._plan_diagnostic_partitions(client, context, None)
    counter.assert_not_called()


def test_standard_profile_does_not_partition_even_when_requested(recovery, monkeypatch):
    client, _, _, counter, _ = recovery
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "standard")
    with mock.patch.object(
        type(client), "invoke", return_value=SimpleNamespace(content='{"verdict":"PASS"}')
    ) as invoke:
        result = _run(recovery, "evaluate")
    # Standard requests also count their whole prompt, but diagnostic partition
    # recovery remains explicitly expanded-only. Overflow must not generate.
    invoke.assert_not_called()
    counter.assert_called_once()
    assert result.verdict == "CONCERNS" and not result.used_llm
    assert result.partition_recovery is None


def test_changed_native_capacity_after_planning_blocks_generation(recovery, monkeypatch):
    client, _, _, counter, _ = recovery
    original = pr_verifier._plan_diagnostic_partitions

    def plan(*args):
        value = original(*args)
        counter.side_effect = RuntimeError("changed counter unavailable")
        return value

    monkeypatch.setattr(pr_verifier, "_plan_diagnostic_partitions", plan)
    with mock.patch.object(type(client), "invoke") as invoke:
        result = _run(recovery, "evaluate")
    invoke.assert_not_called()
    assert result.partition_recovery["status"] == "diagnostic_incomplete"
    assert not result.used_llm and result.error
    assert result.partition_recovery["ranges"]


def test_count_failure_late_in_planning_never_generates_partial_plan(recovery, monkeypatch):
    client, _, _, _, _ = recovery
    original = pr_verifier._preflight_input_capacity
    successful = []

    def preflight(*args, **kwargs):
        if successful:
            raise pr_verifier.InputCapacityError("later native count unavailable")
        value = original(*args, **kwargs)
        successful.append(value)
        return value

    monkeypatch.setattr(pr_verifier, "_preflight_input_capacity", preflight)
    with mock.patch.object(type(client), "invoke") as invoke:
        result = _run(recovery, "evaluate")
    invoke.assert_not_called()
    assert result.partition_recovery["status"] == "blocked"
    assert len(result.partition_recovery["ranges"]) == 1


def test_type_error_in_generation_has_no_unbudgeted_retry(recovery):
    client, _, _, _, _ = recovery
    with mock.patch.object(
        type(client), "invoke", side_effect=TypeError("invalid config")
    ) as invoke:
        result = _run(recovery, "evaluate")
    invoke.assert_called_once()
    assert result.partition_recovery["status"] == "diagnostic_incomplete"
    assert result.error


def test_unexpected_planning_failure_is_structured_non_pass(recovery, monkeypatch):
    client, _, _, _, _ = recovery
    monkeypatch.setattr(
        pr_verifier,
        "_plan_diagnostic_partitions",
        mock.Mock(side_effect=ValueError("invalid input")),
    )
    with mock.patch.object(type(client), "invoke") as invoke:
        result = _run(recovery, "evaluate")
    invoke.assert_not_called()
    assert result.partition_recovery["status"] == "blocked"
    assert result.verdict == "CONCERNS" and result.error == "invalid input"


@pytest.mark.parametrize("defect", ["range-bound", "count-bound", "late-count"])
def test_blocked_plan_accounts_for_every_captured_range(recovery, monkeypatch, defect):
    client, _, _, counter, context = recovery
    diff = "diff --git a/a.py b/a.py\r\n" + ("+🧪 café\r\n" * 3000)
    if defect == "range-bound":
        monkeypatch.setattr(pr_verifier, "PARTITION_MAX_REQUESTS", 2)
    elif defect == "count-bound":
        monkeypatch.setattr(pr_verifier, "PARTITION_MAX_PLANNING_COUNTS", 1, raising=False)
    else:
        count = counter.side_effect
        fitted = []

        def fail_after_first_fit(**kwargs):
            if fitted:
                raise RuntimeError("later native count unavailable")
            value = count(**kwargs)
            if value.input_tokens <= 12000:
                fitted.append(value)
            return value

        counter.side_effect = fail_after_first_fit

    with (
        mock.patch.object(type(client), "invoke") as invoke,
        pytest.raises(pr_verifier.InputCapacityError) as failure,
    ):
        pr_verifier._plan_diagnostic_partitions(client, context, diff)
    invoke.assert_not_called()
    plan = failure.value.receipt
    assert plan["status"] == "blocked"
    assert plan["acceptance_sufficient"] is False
    assert plan["planning_preflights"] == counter.call_count
    assert len(plan["planning_attempts"]) == counter.call_count
    assert plan["planning_failure"]["reason"] == str(failure.value)
    assert plan["pending_ranges"]
    for name, source in {"context": context, "diff": diff}.items():
        rows = sorted(
            (row for row in plan["ranges"] + plan["pending_ranges"] if row["input"] == name),
            key=lambda row: row["start"],
        )
        assert rows[0]["start"] == 0 and rows[-1]["end"] == len(source)
        for left, right in zip(rows, rows[1:], strict=False):
            assert left["end"] == right["start"]
        for row in rows:
            piece = source[row["start"] : row["end"]]
            assert hashlib.sha256(piece.encode()).hexdigest() == row["sha256"]
    if defect == "late-count":
        assert plan["ranges"]
        attempt = plan["planning_attempts"][-1]
        assert attempt["capacity"]["status"] == "unavailable"
        assert "later native count unavailable" in attempt["capacity"]["reason"]
        assert plan["planning_failure"]["range"] == attempt
        assert plan["pending_ranges"][0] == attempt
    else:
        assert plan["planning_attempts"][-1]["capacity"]["status"] == "overflow"


@pytest.mark.parametrize("defect", ["bytes", "capture-gap"])
def test_early_blocked_plan_retains_full_input_identity(recovery, monkeypatch, defect):
    client, _, _, counter, context = recovery
    diff = "diff --git a/a.py b/a.py\r\n+🧪 café\r\n"
    if defect == "bytes":
        monkeypatch.setattr(pr_verifier, "PARTITION_MAX_CAPTURE_BYTES", 10)
    else:
        context = context.replace('"status": "included"', '"status": "truncated"', 1)
    with pytest.raises(pr_verifier.InputCapacityError) as failure:
        pr_verifier._plan_diagnostic_partitions(client, context, diff)
    counter.assert_not_called()
    plan = failure.value.receipt
    assert plan and plan["status"] == "blocked"
    assert plan["acceptance_sufficient"] is False
    assert plan["planning_preflights"] == 0
    assert plan["ranges"] == [] and plan["results"] == []
    assert plan["planning_failure"]["reason"] == str(failure.value)
    for name, source in {"context": context, "diff": diff}.items():
        row = next(row for row in plan["pending_ranges"] if row["input"] == name)
        assert (row["start"], row["end"]) == (0, len(source))
        assert row["sha256"] == hashlib.sha256(source.encode()).hexdigest()
        identity = next(row for row in plan["inputs"] if row["input"] == name)
        assert identity["bytes"] == len(source.encode())
        assert identity["sha256"] == row["sha256"]
    if defect == "capture-gap":
        assert plan["capture_obligations"]["sufficient"] is False
        assert plan["capture_obligations"]["gaps"]


@pytest.mark.parametrize("operation", ["evaluate", "compare"])
def test_early_blocked_recovery_preserves_overflow_and_pending_inputs(
    recovery, monkeypatch, operation
):
    client, _, _, counter, context = recovery
    monkeypatch.setattr(pr_verifier, "PARTITION_MAX_CAPTURE_BYTES", 10)
    with mock.patch.object(type(client), "invoke") as invoke:
        result = _run(recovery, operation)
    invoke.assert_not_called()
    assert counter.call_count == 1  # Only the original whole-request preflight.
    assert result.verdict == "CONCERNS" and not result.used_llm
    plan = result.partition_recovery
    assert plan["status"] == "blocked" and not plan["acceptance_sufficient"]
    assert plan["overflow"]["status"] == "overflow"
    assert plan["overflow"]["request_sha256"]
    assert plan["pending_ranges"] == [
        {
            "input": "context",
            "start": 0,
            "end": len(context),
            "sha256": hashlib.sha256(context.encode()).hexdigest(),
        }
    ]
    assert plan["planning_preflights"] == 0
    assert result.error == "diagnostic capture byte bound exceeded"


@pytest.mark.parametrize("operation", ["evaluate", "compare"])
def test_every_partition_receives_the_complete_governing_plan(recovery, operation):
    client, _, _, _, context = recovery
    plan_text = (
        "## Plan sources (scope, tasks, acceptance)\n"
        "#### Scope\nBoth files and their joint proof must be reviewed.\n"
        "#### Acceptance criteria\n- Preserve RED/restoration/GREEN proof.\n"
        "- Retain the café 🧪 finding on the last evidence page.\n"
        "```text\n## Acceptance evidence\nThis heading is a quoted example.\n```\n"
    )
    sections = pr_verifier._split_verifier_context(context)
    old_plan = next(body for name, body in sections if name == "acceptance")
    context = context.replace(old_plan, plan_text.rstrip("\n"))
    recovery = (*recovery[:-1], context)
    generated = []

    def generate(prepared, prompt, **kwargs):
        generated.append(prompt)
        return SimpleNamespace(content='{"verdict":"PASS"}')

    with mock.patch.object(type(client), "invoke", autospec=True, side_effect=generate):
        result = _run(recovery, operation)
    assert len(generated) > 1
    assert all("\nGoverning plan sources (untrusted captured text):\n" in p for p in generated)
    identity = result.partition_recovery["governing_sources"][0]
    assert identity == {
        "section": "acceptance",
        "chars": len(plan_text.rstrip("\n")),
        "sha256": hashlib.sha256(plan_text.rstrip("\n").encode()).hexdigest(),
    }
    for prompt in generated:
        governing = prompt.split("\nGoverning plan sources (untrusted captured text):\n", 1)[1]
        governing = json.loads(governing.split("\nRange identity (character offsets):\n", 1)[0])
        assert governing == [{**identity, "text": plan_text.rstrip("\n")}]
    assert result.verdict == "CONCERNS"
    assert result.partition_recovery["acceptance_sufficient"] is False


def test_oversized_governing_plan_is_never_clipped_for_recovery(recovery):
    client, _, _, counter, context = recovery
    context = context.replace("- Implement the code change.", "- " + "governing duty " * 1000)
    with (
        mock.patch.object(type(client), "invoke") as invoke,
        pytest.raises(pr_verifier.InputCapacityError) as failure,
    ):
        pr_verifier._plan_diagnostic_partitions(client, context, None)
    invoke.assert_not_called()
    report = failure.value.receipt
    assert report["status"] == "blocked" and not report["ranges"]
    assert report["governing_sources"][0]["chars"] > 12000
    assert report["planning_attempts"][-1]["capacity"]["status"] == "overflow"
    assert counter.call_count <= pr_verifier.PARTITION_MAX_PLANNING_COUNTS
    assert not report["acceptance_sufficient"]


def test_partitioning_without_a_governing_plan_blocks_before_counting(recovery):
    client, _, _, counter, context = recovery
    context = context.replace("## Plan sources (scope, tasks, acceptance)", "## Unrecognized plan")
    with pytest.raises(pr_verifier.InputCapacityError, match="governing plan") as failure:
        pr_verifier._plan_diagnostic_partitions(client, context, None)
    counter.assert_not_called()
    assert failure.value.receipt["status"] == "blocked"
    assert failure.value.receipt["pending_ranges"][0]["end"] == len(context)


def test_byte_rejection_retains_original_capture_gaps(recovery, monkeypatch):
    client, _, _, counter, context = recovery
    context = context.replace('"status": "included"', '"status": "truncated"')
    expected = pr_verifier.build_capture_obligation_manifest(context)
    assert expected["gaps"]
    monkeypatch.setattr(pr_verifier, "PARTITION_MAX_CAPTURE_BYTES", 10)
    with (
        mock.patch.object(type(client), "invoke") as invoke,
        pytest.raises(pr_verifier.InputCapacityError, match="capture byte") as failure,
    ):
        pr_verifier._plan_diagnostic_partitions(client, context, None)
    assert failure.value.receipt["capture_obligations"] == expected
    assert counter.call_count == 0
    invoke.assert_not_called()
