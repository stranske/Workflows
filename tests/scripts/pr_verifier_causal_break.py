"""Causal deliberate-break for the product-component evidence gates.

Temporarily makes ``_required_evidence_channels`` return an empty set, and
separately returns an incoming PASS from ``_apply_coverage_floor`` before
missing-evidence enforcement. The named positive variants must fail, then
pass again after the production file is restored byte-for-byte.

This mutates ``scripts/langchain/pr_verifier.py`` in the worktree. Run it
alone, not under a parallel suite:

    python -m tests.scripts.pr_verifier_causal_break
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from itertools import product
from pathlib import Path

from tests.scripts import test_pr_verifier_delivery_destinations as delivery

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "langchain" / "pr_verifier.py"
RECEIPT_DIR = ROOT / "docs" / "ci" / "verifier-grammar-deliberate-break"
DESTINATIONS = "tests/scripts/test_pr_verifier_delivery_destinations.py"
CHANNEL_TEST = f"{DESTINATIONS}::test_product_component_coordination_preserves_bare_other_channel"
FLOOR_TEST = f"{DESTINATIONS}::test_product_component_coordination_real_floor"

CHANNELS_OLD = """\
def _required_evidence_channels(acceptance: str, *, _bind_attached: bool = True) -> set[str]:
    if len(acceptance) > _EVIDENCE_CACHE_MAX_CHARS:
        return _classify_evidence_channels(acceptance, _bind_attached=_bind_attached)
    return set(_cached_evidence_channels(acceptance, _bind_attached))
"""
CHANNELS_NEW = """\
def _required_evidence_channels(acceptance: str, *, _bind_attached: bool = True) -> set[str]:
    return set()
"""
FLOOR_OLD = """\
def _apply_coverage_floor(
    result: EvaluationResult, coverage: PromptCoverage | None
) -> EvaluationResult:
    \"\"\"Never let a PASS stand on evidence the model did not receive.\"\"\"
    if coverage is None:
        return result
"""
FLOOR_NEW = """\
def _apply_coverage_floor(
    result: EvaluationResult, coverage: PromptCoverage | None
) -> EvaluationResult:
    \"\"\"Never let a PASS stand on evidence the model did not receive.\"\"\"
    if result.verdict == "PASS":
        return result
    if coverage is None:
        return result
"""

_FAILED_NODE = re.compile(r"^FAILED (\S+) - ", re.M)
_SUMMARY = re.compile(
    r"^(?P<counts>\d+ (?:failed|passed|error|errors|skipped)(?:, \d+ \w+)*) in <time>$",
    re.M,
)


def _parametrizations(function):
    return [mark for mark in function.pytestmark if mark.name == "parametrize"]


def channel_node_ids() -> list[str]:
    """Variants whose shared builder requires at least one evidence channel.

    ``test_product_component_coordination_preserves_bare_other_channel`` asserts
    ``_required_evidence_channels`` equals that set. An empty return fails exactly
    these rows: mandatory bare body/comment destinations, and independent artifact
    duties. Rows with an empty requirement still pass under the mutation.
    """
    mark = _parametrizations(
        delivery.test_product_component_coordination_preserves_bare_other_channel
    )[0]
    names = list(mark.args[0])
    nodes = []
    for param in mark.args[1]:
        kwargs = dict(zip(names, param.values, strict=True))
        _criterion, expected, _required = delivery._product_component_case(**kwargs)
        if expected:
            nodes.append(f"{CHANNEL_TEST}[{param.id}]")
    return nodes


def floor_case_kwargs() -> list[dict]:
    """Argument rows of the mapped real-floor integration matrix."""
    marks = _parametrizations(delivery.test_product_component_coordination_real_floor)
    names = [mark.args[0] for mark in marks]
    rows = []
    for combo in product(*(mark.args[1] for mark in marks)):
        rows.append(dict(zip(names, combo, strict=True)))
    return rows


def floor_is_required_absent(kwargs: dict) -> bool:
    """Same ``required`` flag the integration test uses for a CONCERNS verdict.

    The fixture retrieves artifacts and leaves the PR body and comments absent.
    Only the bare-channel obligation (``required``) is unsatisfied evidence.
    An independent artifact duty is present, so those rows still expect PASS.
    """
    _criterion, _expected, required = delivery._product_component_case(
        "UI",
        "generate",
        kwargs["product_channel"],
        "body",
        kwargs["reverse"],
        kwargs["coordination"],
        kwargs["independent"],
        kwargs["governor"],
        kwargs["condition"],
        kwargs["voice"],
    )
    return required


def floor_node_ids() -> list[str]:
    """Required-but-absent rows of ``test_product_component_coordination_real_floor``."""
    marks = _parametrizations(delivery.test_product_component_coordination_real_floor)
    names = [mark.args[0] for mark in marks]
    nodes = []
    for combo in product(*(mark.args[1] for mark in marks)):
        kwargs = dict(zip(names, combo, strict=True))
        if floor_is_required_absent(kwargs):
            suffix = "-".join(str(value) for value in combo)
            nodes.append(f"{FLOOR_TEST}[{suffix}]")
    return nodes


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_transcript(text: str) -> str:
    text = text.replace(str(ROOT), "<repo>")
    text = re.sub(r"\bin [0-9.]+s\b", "in <time>", text)
    return text


def _run_pytest(node_ids: list[str]) -> tuple[int, str]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=line",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            *node_ids,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    transcript = _normalize_transcript(completed.stdout + completed.stderr)
    return completed.returncode, transcript


def _summary_counts(transcript: str) -> str:
    matches = list(_SUMMARY.finditer(transcript))
    if len(matches) != 1:
        raise RuntimeError(f"expected one pytest summary, found {len(matches)}")
    return matches[0]["counts"]


def _failed_nodes(transcript: str) -> list[str]:
    return _FAILED_NODE.findall(transcript)


def _apply(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError("mutation anchor is missing or not unique")
    return text.replace(old, new, 1)


def _write_transcript(name: str, transcript: str) -> None:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    (RECEIPT_DIR / name).write_text(transcript, encoding="utf-8")


def _gate(name: str, old: str, new: str, node_ids: list[str], transcript_stem: str) -> dict:
    original = VERIFIER.read_bytes()
    broken_code = None
    broken_transcript = ""
    try:
        VERIFIER.write_text(_apply(original.decode(), old, new), encoding="utf-8")
        broken_code, broken_transcript = _run_pytest(node_ids)
    finally:
        VERIFIER.write_bytes(original)
    if VERIFIER.read_bytes() != original:
        raise RuntimeError(f"{name} did not restore the verifier")
    restored_code, restored_transcript = _run_pytest(node_ids)
    if VERIFIER.read_bytes() != original:
        raise RuntimeError(f"{name} changed the verifier during the restored run")
    broken_name = f"{transcript_stem}-broken.pytest.txt"
    restored_name = f"{transcript_stem}-restored.pytest.txt"
    _write_transcript(broken_name, broken_transcript)
    _write_transcript(restored_name, restored_transcript)
    return {
        "name": name,
        "node_count": len(node_ids),
        "broken_exit_code": broken_code,
        "broken_summary": _summary_counts(broken_transcript),
        "broken_failed_nodes": _failed_nodes(broken_transcript),
        "restored_exit_code": restored_code,
        "restored_summary": _summary_counts(restored_transcript),
        "broken_transcript": broken_name,
        "restored_transcript": restored_name,
    }


def run() -> dict:
    """Mutate, record failures, restore, record passes, and write the receipt."""
    original = VERIFIER.read_bytes()
    try:
        channels = _gate(
            "required_evidence_channels_empty",
            CHANNELS_OLD,
            CHANNELS_NEW,
            channel_node_ids(),
            "channels",
        )
        floor = _gate(
            "apply_coverage_floor_pass_unchanged",
            FLOOR_OLD,
            FLOOR_NEW,
            floor_node_ids(),
            "floor",
        )
    finally:
        VERIFIER.write_bytes(original)
    if VERIFIER.read_bytes() != original:
        raise RuntimeError("verifier bytes differed after both gates")
    for gate, nodes in (
        (channels, channel_node_ids()),
        (floor, floor_node_ids()),
    ):
        if gate["broken_exit_code"] == 0 or gate["restored_exit_code"] != 0:
            raise RuntimeError(f"{gate['name']} did not fail then pass: {gate}")
        if gate["broken_failed_nodes"] != nodes:
            raise RuntimeError(f"{gate['name']} failed a different node set than requested")
        if gate["broken_summary"] != f"{len(nodes)} failed":
            raise RuntimeError(f"{gate['name']} broken summary was {gate['broken_summary']}")
        if gate["restored_summary"] != f"{len(nodes)} passed":
            raise RuntimeError(f"{gate['name']} restored summary was {gate['restored_summary']}")
    receipt = {
        "source_sha256": _sha256(original),
        "restored_byte_identical": True,
        "python": sys.version.split()[0],
        "mapped_floor_test": FLOOR_TEST,
        "gates": [
            {key: value for key, value in channels.items() if key != "broken_failed_nodes"},
            {key: value for key, value in floor.items() if key != "broken_failed_nodes"},
        ],
    }
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    (RECEIPT_DIR / "receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    receipt = run()
    for gate in receipt["gates"]:
        print(
            f"{gate['name']}: broken {gate['broken_summary']} "
            f"(exit {gate['broken_exit_code']}); "
            f"restored {gate['restored_summary']} (exit {gate['restored_exit_code']})"
        )


if __name__ == "__main__":
    main()
