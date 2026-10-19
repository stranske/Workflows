#!/usr/bin/env python3
"""Reproducible deliberate-break gate for verification-binding audit (#3968).

Applies a temporary Scope change to scripts/langchain/verifier_config.py and a
temporary regression in tests/scripts/test_verifier_config.py, records pass with
the fix, fail when the fix is disconnected, then restores both files
byte-for-byte. Permanent audit PR content stays under docs/reports/ only.

Post-#4129 main already binds via ``\\n\\n---\\n\\n`` separators, but concatenated
report headings without that separator still inherit a historical PASS. Unit
tests ``test_current_main_*`` pin that residual against live main without
mutating production files. The temporary Scope change below selects the last
verifier report heading so the named regression can pass; disconnecting
restores first-heading / full-span selection and the regression must fail.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "scripts" / "langchain" / "verifier_config.py"
TEST_PATH = REPO_ROOT / "tests" / "scripts" / "test_verifier_config.py"
AUDIT_DIR = Path(__file__).resolve().parent
OUT_DIR = AUDIT_DIR / "deliberate-break"
INVENTORY_PATH = AUDIT_DIR / "inventory.json"
REGRESSION_NODE = (
    "tests/scripts/test_verifier_config.py::"
    "test_artifact_from_verification_text_ignores_historical_pass_when_latest_incomplete"
)
POSITIVE_NODE = (
    "tests/scripts/test_verifier_config.py::"
    "test_artifact_from_verification_text_accepts_terminal_verdict_on_latest_report"
)

# Exact heading-selection block from scripts/langchain/verifier_config.py::latest_verifier_report.
_HEADING_SEARCH = (
    "    heading = re.search(\n"
    '        r"^##[ \\t]+(?:PR Verification(?: Report| Comparison)?|LLM Evaluation Report|'
    'Provider Comparison Report)\\b",\n'
    "        raw,\n"
    "        re.I | re.M,\n"
    "    )\n"
    "    return raw[heading.start() :] if heading else raw\n"
)
_HEADING_LAST = (
    "    headings = list(\n"
    "        re.finditer(\n"
    '            r"^##[ \\t]+(?:PR Verification(?: Report| Comparison)?|LLM Evaluation Report|'
    'Provider Comparison Report)\\b",\n'
    "            raw,\n"
    "            re.I | re.M,\n"
    "        )\n"
    "    )\n"
    "    heading = headings[-1] if headings else None\n"
    "    return raw[heading.start() :] if heading else raw\n"
)

REGRESSION_BLOCK = '''

def test_artifact_from_verification_text_ignores_historical_pass_when_latest_incomplete() -> None:
    """Latest incomplete report must not inherit a historical PASS verdict."""

    text = (
        "## PR Verification Report\\nVerdict: PASS\\n\\n"
        "## PR Verification Report\\n"
        "Context extraction failed before any provider returned."
    )
    artifact = artifact_from_verification_text(text)
    assert "verdict" not in artifact
    assert is_terminal_artifact(artifact) is False


def test_artifact_from_verification_text_accepts_terminal_verdict_on_latest_report() -> None:
    """A complete latest report still supplies its own terminal verdict."""

    text = (
        "## PR Verification Report\\nVerdict: FAIL\\n\\n"
        "## PR Verification Report\\nVerdict: PASS\\n"
    )
    artifact = artifact_from_verification_text(text)
    assert artifact.get("verdict") == "PASS"
    assert is_terminal_artifact(artifact) is True
'''


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_transcript(blob: bytes) -> bytes:
    """Drop pytest wall-clock noise so deliberate-break receipts stay reproducible."""

    text = blob.decode("utf-8", errors="replace")
    # "2 passed in 0.94s" / "1 failed in 0.23s" — duration is not evidence.
    text = re.sub(
        r"\b(\d+ (?:passed|failed|skipped|xfailed|xpassed|error|errors)) in [0-9.]+s\b",
        r"\1 in <time>",
        text,
    )
    # Rare pytest variants: "in 1.23s =" suffixes on progress lines.
    text = re.sub(r"\bin [0-9.]+s\b", "in <time>", text)
    return text.encode("utf-8")


def _write_transcript(name: str, payload: bytes) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_transcript(payload)
    path = OUT_DIR / name
    path.write_bytes(normalized)
    digest = _sha256_bytes(normalized)
    (OUT_DIR / f"{name}.sha256").write_text(digest + "\n", encoding="utf-8")
    return digest


def _run_pytest(nodes: list[str]) -> subprocess.CompletedProcess[bytes]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *nodes,
        "-o",
        "addopts=",
        "-m",
        "not slow",
    ]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True)


def _summarize_pytest(blob: bytes) -> str:
    text = _normalize_transcript(blob).decode("utf-8", errors="replace")
    for pattern, label in (
        (r"(\d+) failed", "failed"),
        (r"(\d+) passed", "passed"),
    ):
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)} {label}"
    raise RuntimeError("could not summarize pytest transcript:\n" + text)


def _apply_scope_fix(source: str) -> str:
    """Select the last verifier report heading (Scope change for #3966 residual)."""

    if _HEADING_SEARCH not in source:
        raise RuntimeError("failed to locate latest_verifier_report first-heading selection block")
    if source.count(_HEADING_SEARCH) != 1:
        raise RuntimeError("latest_verifier_report heading selection block is not unique")
    return source.replace(_HEADING_SEARCH, _HEADING_LAST, 1)


def _disconnect_scope_fix(fixed: str) -> str:
    """Restore first-heading selection while keeping the temporary tests."""

    if _HEADING_LAST not in fixed:
        raise RuntimeError("failed to locate last-heading Scope change for deliberate-break")
    if fixed.count(_HEADING_LAST) != 1:
        raise RuntimeError("last-heading Scope change block is not unique")
    return fixed.replace(_HEADING_LAST, _HEADING_SEARCH, 1)


def test_scope_fix_transforms_round_trip_on_current_verifier_config() -> None:
    """Planning-harness unit check: apply then disconnect restores the source file."""

    original = CONFIG_PATH.read_text(encoding="utf-8")
    fixed = _apply_scope_fix(original)
    assert fixed != original
    assert "re.finditer(" in fixed
    assert "headings[-1]" in fixed
    restored = _disconnect_scope_fix(fixed)
    assert restored == original


def test_scope_fix_blocks_are_present_in_current_verifier_config() -> None:
    """Fail loudly if main moves the heading-selection anchor this harness patches."""

    source = CONFIG_PATH.read_text(encoding="utf-8")
    assert _HEADING_SEARCH in source


def test_current_main_inherits_historical_pass_without_separator() -> None:
    """Residual #3966 gap on current main: concatenated headings still inherit PASS.

    Post-#4129 separator-aware binding is covered by
    ``test_current_main_separator_blocks_historical_pass``; this case is the
    deliberate-break disconnect failure mode without applying the Scope change.
    """

    from scripts.langchain.verifier_config import (
        artifact_from_verification_text,
        is_terminal_artifact,
    )

    text = (
        "## PR Verification Report\nVerdict: PASS\n\n"
        "## PR Verification Report\n"
        "Context extraction failed before any provider returned."
    )
    artifact = artifact_from_verification_text(text)
    assert artifact.get("verdict") == "PASS"
    assert is_terminal_artifact(artifact) is True


def test_current_main_separator_blocks_historical_pass() -> None:
    """#4129 separator path on current main must not reuse a prior PASS."""

    from scripts.langchain.verifier_config import (
        artifact_from_verification_text,
        is_terminal_artifact,
    )

    text = (
        "## PR Verification Report\nVerdict: PASS\n\n---\n\n"
        "## PR Verification Report\n"
        "Context extraction failed before any provider returned."
    )
    artifact = artifact_from_verification_text(text)
    assert "verdict" not in artifact
    assert is_terminal_artifact(artifact) is False


def _scope_change_description() -> str:
    return (
        "scripts/langchain/verifier_config.py latest_verifier_report: "
        "select last verifier report heading (re.finditer) instead of first (re.search)"
    )


def _residual_gap_description() -> str:
    return (
        "post-#4129 main still inherits historical PASS for concatenated headings "
        "without \\n\\n---\\n\\n; owned by #3966"
    )


def test_inventory_deliberate_break_matches_harness_scope_change() -> None:
    """Inventory deliberate_break must describe the same Scope change as this harness."""

    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    block = inventory["deliberate_break"]
    assert block["scope_change"] == _scope_change_description()
    assert block["residual_gap"] == _residual_gap_description()
    receipt = json.loads((OUT_DIR / "receipt.json").read_text(encoding="utf-8"))
    assert block["scope_change"] == receipt["scope_change"]
    assert block["with_fix"]["sha256"] == receipt["with_fix"]["sha256"]
    assert block["fix_disconnected"]["sha256"] == receipt["fix_disconnected"]["sha256"]
    assert block["fix_restored"]["sha256"] == receipt["fix_restored"]["sha256"]


# Issue #3968 has both ## Why and ## Scope. issue_scope_parser aliases Why→Scope and
# headings.find() keeps the first match, so keepalive extractScopePatterns sees defect
# file paths instead of `docs/reports/`. That falsely marks this report-only PR as a
# scope-violation and blocks tasks-complete. Authoritative deliverable Scope must list
# docs/reports/; repaired PR Scope text is pinned below for restore after meta upsert.
AUTHORITATIVE_ISSUE_SCOPE = (
    "- Audit Workflows-owned workflows, scripts and managed templates that convert "
    "verify labels, verification comments, terminal artifacts or request markers into "
    "completion, follow-up eligibility or reported acceptance.\n"
    "- Produce the verification-binding audit report under `docs/reports/` with the "
    "source commit, search inventory and exclusions, and a classification per instance.\n"
    "- File follow-up issues for unresolved instances beyond the two existing "
    "per-instance candidates."
)
WHY_AS_SCOPE_TEXT = (
    "Two verified gaps share one defect: a verification-state consumer treats an unbound "
    "or historical signal as current evidence. `scripts/langchain/verifier_config.py:140` "
    "promotes an old verdict into follow-up eligibility despite a newer incomplete report, "
    "and `.github/workflows/agents-auto-pilot.yml:2344` with "
    "`.github/scripts/auto_pilot_transitions.js:98` promotes an issue-only "
    "`verify:evaluate` label into completed handoff with no merged PR."
)
REPAIRED_PR_SCOPE = (
    "Audit deliverables for this PR are report/planning artifacts under `docs/reports/` "
    "(including `docs/reports/verification-binding-audit.md` and "
    "`docs/reports/verification-binding-audit/`).\n\n"
    "Problem being audited (not in-diff production fixes): a verification-state consumer "
    "treats an unbound or historical signal as current evidence. Known sites: "
    "`scripts/langchain/verifier_config.py` (#3966) and "
    "`.github/workflows/agents-auto-pilot.yml` / `.github/scripts/auto_pilot_transitions.js` "
    "(#3967). Produce the verification-binding audit report under `docs/reports/` with the "
    "source commit, search inventory and exclusions, and a classification per instance. "
    "File follow-up issues for unresolved instances beyond the two existing per-instance "
    "candidates.\n\n"
    "Current source readback retained for provenance: "
    "`scripts/langchain/verifier_config.py:126` at "
    "`24bf36fe81333dd3c028cf1bb47b333fecdd2580`."
)
AUDIT_DELIVERABLE_FILES = (
    "docs/reports/verification-binding-audit.md",
    "docs/reports/verification-binding-audit/deliberate_break_gate.py",
    "docs/reports/verification-binding-audit/inventory.json",
    "docs/reports/verification-binding-audit/deliberate-break/receipt.json",
)


def _keepalive_scope_compliance(scope_text: str, files: list[str]) -> dict:
    """Run keepalive_loop extractScopePatterns + validateScopeCompliance via node."""

    payload = json.dumps({"scope": scope_text, "files": files})
    script = (
        "const { extractScopePatterns, validateScopeCompliance } = "
        "require('./.github/scripts/keepalive_loop.js');"
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "const patterns = extractScopePatterns(input.scope);"
        "process.stdout.write(JSON.stringify({"
        "patterns, ...validateScopeCompliance(input.files, patterns)"
        "}));"
    )
    proc = subprocess.run(
        ["node", "-e", script],
        cwd=REPO_ROOT,
        input=payload.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "keepalive scope probe failed:\n" + proc.stderr.decode("utf-8", errors="replace")
        )
    return json.loads(proc.stdout.decode("utf-8"))


def test_why_as_scope_falsely_rejects_audit_deliverables() -> None:
    """Document the Why→Scope alias hazard that blocked keepalive tasks-complete."""

    result = _keepalive_scope_compliance(WHY_AS_SCOPE_TEXT, list(AUDIT_DELIVERABLE_FILES))
    assert result["compliant"] is False
    assert result["outOfScope"] == list(AUDIT_DELIVERABLE_FILES)
    assert not any(p.startswith("docs/reports") for p in result["patterns"])


def test_authoritative_issue_scope_accepts_audit_deliverables() -> None:
    """Issue ## Scope (docs/reports/) must accept every audit PR path."""

    result = _keepalive_scope_compliance(AUTHORITATIVE_ISSUE_SCOPE, list(AUDIT_DELIVERABLE_FILES))
    assert result["compliant"] is True
    assert result["outOfScope"] == []
    assert "docs/reports/" in result["patterns"]


def test_repaired_pr_scope_accepts_audit_deliverables() -> None:
    """PR auto-status Scope must keep docs/reports/ after Why-alias clobber recovery."""

    result = _keepalive_scope_compliance(REPAIRED_PR_SCOPE, list(AUDIT_DELIVERABLE_FILES))
    assert result["compliant"] is True
    assert result["outOfScope"] == []
    assert any(p.startswith("docs/reports") for p in result["patterns"])


def main() -> int:
    original_config = CONFIG_PATH.read_bytes()
    original_test = TEST_PATH.read_bytes()
    original_config_text = original_config.decode("utf-8")
    original_test_text = original_test.decode("utf-8")

    marker = "test_artifact_from_verification_text_ignores_historical_pass_when_latest_incomplete"
    if marker in original_test_text:
        raise RuntimeError(
            "regression already present in working tree; aborting to avoid double-append"
        )

    try:
        fixed_config = _apply_scope_fix(original_config_text)
        CONFIG_PATH.write_text(fixed_config, encoding="utf-8")
        TEST_PATH.write_text(original_test_text + REGRESSION_BLOCK, encoding="utf-8")

        with_fix = _run_pytest([REGRESSION_NODE, POSITIVE_NODE])
        with_fix_blob = with_fix.stdout + b"\n--- stderr ---\n" + with_fix.stderr
        with_fix_sha = _write_transcript("with_fix.pytest.txt", with_fix_blob)
        if with_fix.returncode != 0:
            raise RuntimeError(
                f"expected with-fix run to pass, got {with_fix.returncode}:\n"
                + with_fix_blob.decode("utf-8", errors="replace")
            )

        CONFIG_PATH.write_text(_disconnect_scope_fix(fixed_config), encoding="utf-8")
        # Scope AC targets the historical-PASS regression only when disconnected.
        disconnected = _run_pytest([REGRESSION_NODE])
        disconnected_blob = disconnected.stdout + b"\n--- stderr ---\n" + disconnected.stderr
        disconnected_sha = _write_transcript("fix_disconnected.pytest.txt", disconnected_blob)
        if disconnected.returncode == 0:
            raise RuntimeError(
                "expected disconnected Scope change to fail the historical-PASS regression"
            )
        disconnected_text = disconnected_blob.decode("utf-8", errors="replace")
        if "verdict" not in disconnected_text or "PASS" not in disconnected_text:
            raise RuntimeError(
                "disconnected failure did not show inherited PASS/verdict assertion:\n"
                + disconnected_text
            )
        if "AssertionError" not in disconnected_text:
            raise RuntimeError(
                "disconnected run did not fail with AssertionError:\n" + disconnected_text
            )

        CONFIG_PATH.write_text(fixed_config, encoding="utf-8")
        restored = _run_pytest([REGRESSION_NODE, POSITIVE_NODE])
        restored_blob = restored.stdout + b"\n--- stderr ---\n" + restored.stderr
        restored_sha = _write_transcript("fix_restored.pytest.txt", restored_blob)
        if restored.returncode != 0:
            raise RuntimeError(
                f"expected restored Scope change to pass, got {restored.returncode}:\n"
                + restored_blob.decode("utf-8", errors="replace")
            )
    finally:
        CONFIG_PATH.write_bytes(original_config)
        TEST_PATH.write_bytes(original_test)

    if CONFIG_PATH.read_bytes() != original_config or TEST_PATH.read_bytes() != original_test:
        raise RuntimeError("working tree not restored byte-for-byte")

    # Idempotence guard: normalized transcripts must hash stably across re-runs.
    for label, blob, digest in (
        ("with_fix", with_fix_blob, with_fix_sha),
        ("fix_disconnected", disconnected_blob, disconnected_sha),
        ("fix_restored", restored_blob, restored_sha),
    ):
        again = _sha256_bytes(_normalize_transcript(blob))
        if again != digest:
            raise RuntimeError(f"transcript normalization not idempotent for {label}")

    scope_change = _scope_change_description()
    residual_gap = _residual_gap_description()
    disconnected_assertion = (
        "assert 'verdict' not in artifact; observed verdict PASS from historical report"
    )
    receipt = {
        "regression": REGRESSION_NODE,
        "positive_control": POSITIVE_NODE,
        "scope_change": scope_change,
        "residual_gap": residual_gap,
        "transcript_normalization": "pytest wall-clock durations replaced with <time>",
        "with_fix": {
            "result": _summarize_pytest(with_fix_blob),
            "sha256": with_fix_sha,
        },
        "fix_disconnected": {
            "result": _summarize_pytest(disconnected_blob),
            "assertion": disconnected_assertion,
            "sha256": disconnected_sha,
        },
        "fix_restored": {
            "result": _summarize_pytest(restored_blob),
            "sha256": restored_sha,
        },
        "working_tree_restored": True,
        "config_sha256_after": _sha256_bytes(CONFIG_PATH.read_bytes()),
        "test_sha256_after": _sha256_bytes(TEST_PATH.read_bytes()),
    }
    receipt_path = OUT_DIR / "receipt.json"
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)

    # Keep inventory deliberate_break evidence aligned with the receipt (same Scope change,
    # transcript digests, and residual-gap note). Prior retarget left inventory stale.
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    inventory["deliberate_break"] = {
        "harness": "docs/reports/verification-binding-audit/deliberate_break_gate.py",
        "regression": REGRESSION_NODE,
        "positive_control": POSITIVE_NODE,
        "scope_change": scope_change,
        "residual_gap": residual_gap,
        "transcript_normalization": receipt["transcript_normalization"],
        "with_fix": {
            "result": receipt["with_fix"]["result"],
            "sha256": with_fix_sha,
            "transcript": "docs/reports/verification-binding-audit/deliberate-break/with_fix.pytest.txt",
        },
        "fix_disconnected": {
            "result": receipt["fix_disconnected"]["result"],
            "assertion": disconnected_assertion,
            "sha256": disconnected_sha,
            "transcript": (
                "docs/reports/verification-binding-audit/deliberate-break/"
                "fix_disconnected.pytest.txt"
            ),
        },
        "fix_restored": {
            "result": receipt["fix_restored"]["result"],
            "sha256": restored_sha,
            "transcript": "docs/reports/verification-binding-audit/deliberate-break/fix_restored.pytest.txt",
        },
        "working_tree_restored": True,
        "config_sha256_after": receipt["config_sha256_after"],
        "test_sha256_after": receipt["test_sha256_after"],
        "receipt": "docs/reports/verification-binding-audit/deliberate-break/receipt.json",
        "post_audit_note": (
            "After source e9b9424b, PR #4129 merged separator-aware latest-report binding on "
            "main; concatenated headings without \\n\\n---\\n\\n still inherit historical PASS "
            "(owned by #3966). This audit PR ships only report/planning artifacts; the harness "
            "temporarily applies last-heading selection, proves disconnect failure, then restores "
            "byte-for-byte."
        ),
    }
    INVENTORY_PATH.write_text(
        json.dumps(inventory, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
