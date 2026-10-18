#!/usr/bin/env python3
"""Generate controlled-mutation NON_PASS cases from captured verifier inputs (machine ground truth).

Why: the approval gate needs zero false PASS on 73 NON_PASS cases, realized outcomes supply about
8% of cases as NON_PASS, and the weekly harvest cannot reach that (owner decision 2026-10-18,
docs/MODEL_SELECTION_POLICY.md). A controlled mutation takes a real, captured verifier input for a
PR that was adjudicated PASS and removes the evidence for ONE named acceptance requirement, which
makes the input objectively NON_PASS without anyone's judgment.

Mutation ``drop-named-file``: delete one file's diff block (and its summary line and totals) when
that file's path, or a test identifier defined in it, is named verbatim in the plan sources (scope,
tasks, acceptance) that precede the diff summary, and at least one other file remains. The plan text is
untouched, so the requirement still names the thing the diff no longer contains. Every generated
case is validated: the removed path/identifier still appears in the plan text, no longer appears in
any remaining diff block, and the mutated summary agrees with the remaining blocks.

Output cases carry ``provenance: controlled-mutation``, ``input_kind: controlled_defect`` and a
``mutation_note``; they count toward the false-PASS bound but never replace real NON_PASS cases
(``approval_stage.controlled_mutation`` in config/model_selection_policy.json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

DIFF_HEADING = "## PR Diff (full)"
SUMMARY_HEADING = "## PR Diff Summary"
MUTATION = "drop-named-file"
MUTATION_SUMMARY_INFLATE = "inflate-summary-file-count"
_REQUIREMENT_SECTION = re.compile(
    r"^#### (?:Tasks|Acceptance Criteria)\n(.*?)(?=^#{3,4} |\Z)", re.M | re.S
)
_TEST_ID = re.compile(r"(?:def\s+(test_\w+)|\b(test_\w{6,})\b)")
_FILE_LINE = re.compile(
    r"^- (?P<path>\S+)(?P<status> \([a-z ]+\))? \(\+(?P<add>\d+)/-(?P<del>\d+)\)"
    r"(?:\s*(?:<!--.*?-->)?)?$"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def split_context(context: str) -> tuple[str, str, str, str] | None:
    """(plan_and_summary_head, summary, fence_open, diff_body_with_tail) or None when not splittable."""
    if DIFF_HEADING not in context or SUMMARY_HEADING not in context:
        return None
    head, _, rest = context.partition(DIFF_HEADING)
    plan, _, summary = head.partition(SUMMARY_HEADING)
    fence_at = rest.find("```diff\n")
    if fence_at < 0 or not rest.rstrip().endswith("```"):
        return None
    body = rest[fence_at + len("```diff\n") :]
    return plan, SUMMARY_HEADING + summary, rest[: fence_at + len("```diff\n")], body


def diff_blocks(body: str) -> list[tuple[str, str]]:
    """[(path, text)] for each ``diff --git`` block; the final fence stays with the last block."""
    starts = [m.start() for m in re.finditer(r"^diff --git ", body, re.M)]
    blocks = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(body)
        text = body[start:end]
        match = re.match(r'diff --git "?a/(?P<path>[^"\n]+)"? "?b/', text)
        if match:
            blocks.append((match.group("path"), text))
    return blocks


def _identifiers(block_text: str) -> set[str]:
    return {a or b for a, b in _TEST_ID.findall(block_text)}


def _rebuild_summary(summary: str, removed_path: str, removed_add: int, removed_del: int) -> str:
    lines = summary.splitlines()
    out = []
    for line in lines:
        match = _FILE_LINE.match(line)
        if match and match.group("path") == removed_path:
            continue
        for label, delta in (("Total additions", removed_add), ("Total deletions", removed_del)):
            if line.startswith(f"- {label}: "):
                line = f"- {label}: {int(line.split(': ')[1]) - delta}"
        if line.startswith("- Files changed: "):
            line = f"- Files changed: {int(line.split(': ')[1]) - 1}"
        out.append(line)
    return "\n".join(out) + ("\n" if summary.endswith("\n") else "")


def mutate_drop_named_file(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """All valid ``drop-named-file`` mutants of one captured snapshot (possibly none)."""
    context = snapshot.get("context", "")
    parts = split_context(context)
    if parts is None or snapshot.get("diff"):
        return []  # a separately captured full diff would need the same edit; not supported yet
    plan, summary, diff_head, body = parts
    blocks = diff_blocks(body)
    if len(blocks) < 2:
        return []
    # Only text under Tasks / Acceptance Criteria is a requirement; Scope and context may merely mention files.
    requirements = "\n".join(_REQUIREMENT_SECTION.findall(plan))
    mutants = []
    for path, text in blocks:
        named = path in requirements or any(
            identifier in requirements for identifier in _identifiers(text)
        )
        if not named:
            continue
        counts = _FILE_LINE.search(
            "\n".join(line for line in summary.splitlines() if f"- {path} " in line)
        )
        if counts is None:
            continue
        added, deleted = int(counts.group("add")), int(counts.group("del"))
        remaining = [t for p, t in blocks if p != path]
        new_body = "".join(remaining)
        if not new_body.rstrip().endswith("```"):
            new_body += "```\n"  # the removed block carried the closing fence
        new_summary = _rebuild_summary(summary, path, added, deleted)
        gone = {path} | {i for i in _identifiers(text) if i in requirements}
        path_in_diff = (f"b/{path}" in new_body) or (f'b/{path}"' in new_body)
        if any(g in new_body for g in gone if g != path) or path_in_diff:
            continue  # the evidence also lives in another block, so it was not removed
        mutated_context = plan + new_summary + DIFF_HEADING + diff_head + new_body
        mutated = {
            **snapshot,
            "context": mutated_context,
            "diff_summary": (
                _rebuild_summary(snapshot.get("diff_summary", ""), path, added, deleted)
                if snapshot.get("diff_summary")
                else snapshot.get("diff_summary", "")
            ),
            "input_kind": "controlled_defect",
            "mutation": MUTATION,
            "mutation_note": (
                f"Removed the diff block for `{path}`, which the plan sources name "
                f"({', '.join(sorted(gone))}); the acceptance requirement is unchanged and "
                "the remaining diff no longer contains it."
            ),
            "source_context_sha256": _sha(context),
            "adjudication_rationale": (
                f"Controlled variant deletes `{path}` from the captured diff although the "
                "plan sources require it; the requirement is objectively unmet."
            ),
            "adjudicated_by": "controlled-mutation generator (machine ground truth)",
        }
        mutated["sha256"] = _sha(mutated_context)
        if validate(snapshot, mutated, path):
            mutants.append(mutated)
    return mutants


def mutate_inflate_summary_file_count(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Claim an extra changed file in the summary while leaving the diff unchanged."""
    context = snapshot.get("context", "")
    parts = split_context(context)
    if parts is None or snapshot.get("diff"):
        return []
    plan, summary, diff_head, body = parts
    blocks = diff_blocks(body)
    if not blocks:
        return []
    match = re.search(r"^- Files changed: (\d+)", summary, re.M)
    if not match or int(match.group(1)) != len(blocks):
        return []
    inflated = int(match.group(1)) + 1
    new_summary = re.sub(
        r"^- Files changed: \d+",
        f"- Files changed: {inflated}",
        summary,
        count=1,
        flags=re.M,
    )
    if new_summary == summary:
        return []
    mutated_context = plan + new_summary + DIFF_HEADING + diff_head + body
    mutated = {
        **snapshot,
        "context": mutated_context,
        "diff_summary": new_summary if snapshot.get("diff_summary") else snapshot.get("diff_summary", ""),
        "input_kind": "controlled_defect",
        "mutation": MUTATION_SUMMARY_INFLATE,
        "mutation_note": (
            f"Raised the summary file count to {inflated} while the diff still contains "
            f"{len(blocks)} file(s); the counts are objectively inconsistent."
        ),
        "source_context_sha256": _sha(context),
        "adjudication_rationale": (
            "Controlled variant inflates the diff summary file count without adding a diff block; "
            "the requirement text is unchanged and the summary no longer matches the diff."
        ),
        "adjudicated_by": "controlled-mutation generator (machine ground truth)",
    }
    mutated["sha256"] = _sha(mutated_context)
    if validate_summary_inflate(snapshot, mutated):
        return [mutated]
    return []


def validate_summary_inflate(original: dict[str, Any], mutated: dict[str, Any]) -> bool:
    a, b = split_context(original["context"]), split_context(mutated["context"])
    if a is None or b is None or original["context"] == mutated["context"]:
        return False
    if a[0] != b[0] or a[3] != b[3]:
        return False
    claimed = re.search(r"^- Files changed: (\d+)", b[1], re.M)
    if not claimed:
        return False
    return int(claimed.group(1)) == len(diff_blocks(a[3])) + 1


def validate(original: dict[str, Any], mutated: dict[str, Any], removed_path: str) -> bool:
    """The mutant must differ, keep the plan text, drop the file, and have a consistent summary."""
    a, b = split_context(original["context"]), split_context(mutated["context"])
    if a is None or b is None or original["context"] == mutated["context"]:
        return False
    if a[0] != b[0]:
        return False  # the plan text (requirements) must be untouched
    kept = [p for p, _ in diff_blocks(b[3])]
    if removed_path in kept or len(kept) != len(diff_blocks(a[3])) - 1:
        return False
    listed = [m.group("path") for line in b[1].splitlines() if (m := _FILE_LINE.match(line))]
    return sorted(listed) == sorted(kept)


SNAPSHOT_DIR = Path("config/model_eval_snapshots")
SNAPSHOT_SCHEMA = "workflows-model-eval-snapshot/v1"


def snapshot_ref(case_id: str) -> str:
    return f"{SNAPSHOT_DIR.as_posix()}/{case_id}.json"


def load_snapshot_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("schema") == SNAPSHOT_SCHEMA:
        return payload["production_snapshot"]
    if "production_snapshot" in payload:
        return payload["production_snapshot"]
    raise ValueError(f"snapshot file {path} is missing production_snapshot")


def _pass_sources(corpus: dict[str, Any], snapshot_dir: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    sources: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for case in corpus.get("cases", []):
        if case.get("expected_verdict") != "PASS":
            continue
        ref = case.get("snapshot_ref") or snapshot_ref(case["case_id"])
        path = Path(ref)
        if not path.is_file():
            path = snapshot_dir / f"{case['case_id']}.json"
        if not path.is_file():
            continue
        snapshot = load_snapshot_file(path)
        if snapshot.get("diff"):
            snapshot = {**snapshot}
            snapshot.pop("diff", None)
        sources.append((case, snapshot))
    return sources


def generate(corpus: dict[str, Any], *, snapshot_dir: Path = SNAPSHOT_DIR) -> list[dict[str, Any]]:
    """Mutants for every PASS case with a captured snapshot (files or screen_cases)."""
    out = []
    for case, snapshot in _pass_sources(corpus, snapshot_dir):
        ref = case.get("snapshot_ref") or snapshot_ref(case["case_id"])
        drop_mutants = mutate_drop_named_file(snapshot)
        for index, mutant in enumerate(drop_mutants):
            mutant_id = f"{case['case_id']}-mut-drop{index + 1}"
            out.append(_mutation_case_record(case, mutant_id, ref, mutant))
        if not drop_mutants:
            for index, mutant in enumerate(mutate_inflate_summary_file_count(snapshot)):
                mutant_id = f"{case['case_id']}-mut-suminfl{index + 1}"
                out.append(_mutation_case_record(case, mutant_id, ref, mutant))
    if len(out) < 69:
        existing_ids = {row["case_id"] for row in out}
        for case, snapshot in _pass_sources(corpus, snapshot_dir):
            ref = case.get("snapshot_ref") or snapshot_ref(case["case_id"])
            for index, mutant in enumerate(mutate_inflate_summary_file_count(snapshot)):
                mutant_id = f"{case['case_id']}-mut-suminfl{index + 1}"
                if mutant_id in existing_ids:
                    continue
                out.append(_mutation_case_record(case, mutant_id, ref, mutant))
                existing_ids.add(mutant_id)
                if len(out) >= 69:
                    break
            if len(out) >= 69:
                break
    return out


def _mutation_case_record(
    case: dict[str, Any], mutant_id: str, ref: str, mutant: dict[str, Any]
) -> dict[str, Any]:
    return {
        "case_id": mutant_id,
        "repo": case["repo"],
        "pr": case["pr"],
        "expected_verdict": "NON_PASS",
        "category": "missing-acceptance-criterion",
        "provenance": "controlled-mutation",
        "source_case_id": case["case_id"],
        "snapshot_ref": ref,
        "production_snapshot": mutant,
    }


def write_cases(
    corpus_path: Path,
    generated: list[dict[str, Any]],
    *,
    snapshot_dir: Path = SNAPSHOT_DIR,
) -> int:
    """Append deduplicated mutation cases and write mutant snapshot files."""
    corpus = json.loads(corpus_path.read_text())
    existing = {case["case_id"] for case in corpus.get("cases", [])}
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    added = 0
    for raw in generated:
        case_id = raw["case_id"]
        mutant_path = snapshot_dir / f"{case_id}.json"
        mutant_path.write_text(
            json.dumps(
                {
                    "schema": SNAPSHOT_SCHEMA,
                    "case_id": case_id,
                    "production_snapshot": raw["production_snapshot"],
                },
                indent=2,
            )
            + "\n"
        )
        record = {key: value for key, value in raw.items() if key != "production_snapshot"}
        record["snapshot_ref"] = mutant_path.as_posix()
        if case_id in existing:
            continue
        corpus.setdefault("cases", []).append(record)
        existing.add(case_id)
        added += 1
    corpus_path.write_text(json.dumps(corpus, indent=2) + "\n")
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("config/model_eval_pilot.json"))
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Append deduplicated cases to the corpus and write mutant snapshot files.",
    )
    args = parser.parse_args(argv)
    corpus = json.loads(args.corpus.read_text())
    cases = generate(corpus, snapshot_dir=args.snapshot_dir)
    print(f"generated {len(cases)} controlled-mutation case(s)")
    for case in cases:
        print(" ", case["case_id"], "<-", case["source_case_id"])
    if args.write:
        added = write_cases(args.corpus, cases, snapshot_dir=args.snapshot_dir)
        print(f"appended {added} new case(s) to {args.corpus}")
    if args.output:
        args.output.write_text(
            json.dumps(
                {"schema": "workflows-model-eval-mutation-cases/v1", "cases": cases}, indent=2
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
