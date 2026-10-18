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
import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.create_model_eval_snapshot import create_case
from tools.model_eval_snapshots import snapshot_digest

DIFF_HEADING = "## PR Diff (full)"
SUMMARY_HEADING = "## PR Diff Summary"
MUTATION = "drop-named-file"
_REQUIREMENT_SECTION = re.compile(
    r"^#### (?:Tasks|Acceptance Criteria)\n(.*?)(?=^#{3,4} |\Z)", re.M | re.S
)
_TEST_ID = re.compile(r"(?:def\s+(test_\w+)|\b(test_\w{6,})\b)")
_FILE_LINE = re.compile(
    r"^- (?P<path>\S+)(?P<status> \([a-z ]+\))? \(\+(?P<add>\d+)/-(?P<del>\d+)\)(?: <!--.*-->)?$"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _digest(snapshot: dict[str, Any]) -> str:
    """The corpus digest for complete snapshots; a content hash for partial ones (tests)."""
    try:
        return snapshot_digest(snapshot)
    except KeyError:
        return _sha(snapshot.get("context", "") + snapshot.get("diff", ""))


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
        match = re.match(r"diff --git a/(\S+) b/\S+", text)
        if match:
            blocks.append((match.group(1), text))
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
    if parts is None:
        return []
    patch = snapshot.get("diff")
    patch_blocks = diff_blocks(patch) if patch else []
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
        if any(g in new_body for g in gone if g != path) or f"b/{path}" in new_body:
            continue  # the evidence also lives in another block, so it was not removed
        new_patch = None
        if patch:
            if len(patch_blocks) < 2 or path not in {p for p, _ in patch_blocks}:
                continue
            new_patch = "".join(t for p, t in patch_blocks if p != path)
            if any(g in new_patch for g in gone if g != path) or f"b/{path}" in new_patch:
                continue
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
            "mutation_path": path,
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
        if new_patch is not None:
            mutated["diff"] = new_patch
        mutated["sha256"] = _digest(mutated)
        if validate(snapshot, mutated, path):
            mutants.append(mutated)
    return mutants


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
    if original.get("diff"):
        patch_kept = [p for p, _ in diff_blocks(mutated.get("diff", ""))]
        if removed_path in patch_kept or sorted(patch_kept) != sorted(kept):
            return False
    listed = [m.group("path") for line in b[1].splitlines() if (m := _FILE_LINE.match(line))]
    return sorted(listed) == sorted(kept)


SNAPSHOT_DIR = Path("config/model_eval_snapshots")


def corpus_case_for(corpus: dict[str, Any], repo: str, pr: int) -> dict[str, Any] | None:
    """The corpus case for a captured PR (repository and PR number, case-insensitive repo)."""
    for case in corpus.get("cases", []):
        if str(case.get("repo", "")).lower() == repo.lower() and str(case.get("pr")) == str(pr):
            return case
    return None


def snapshots_from_artifacts(
    corpus: dict[str, Any], artifact_roots: list[Path]
) -> dict[str, dict[str, Any]]:
    """case_id -> full case (with production_snapshot) for each captured PASS corpus case.

    ``artifact_roots`` are directories holding ``captured-inputs/case-N`` (a MAINT-78 capture
    artifact). A captured PR that is not a PASS case in the corpus is skipped.
    """
    out: dict[str, dict[str, Any]] = {}
    for root in artifact_roots:
        for manifest_path in sorted(
            root.glob("captured-inputs/case-*/verifier-input-manifest.json")
        ):
            manifest = json.loads(manifest_path.read_text())
            case = corpus_case_for(corpus, manifest["repository"], manifest["pr"])
            if case is None or case.get("expected_verdict") != "PASS":
                continue
            out[case["case_id"]] = create_case(
                manifest_path.parent,
                case_id=case["case_id"],
                expected_verdict="PASS",
                category=case["category"],
                adjudication_evidence=f"https://github.com/{manifest['repository']}/pull/{manifest['pr']}",
                adjudicated_by="realized-outcome harvest (corpus case)",
                adjudication_rationale=(
                    f"Corpus case {case['case_id']} ({case['category']}): the merged PR was "
                    "adjudicated PASS by realized outcome; the input is replayed unmodified."
                ),
            )
    return out


MAX_PER_SOURCE = 3  # mutants of one PR share almost all their input: not independent cases


def _is_test_path(path: str) -> bool:
    return "/tests/" in f"/{path}" or "__tests__" in path or Path(path).name.startswith("test_")


def generate_from_snapshots(
    snapshots: dict[str, dict[str, Any]], max_per_source: int = MAX_PER_SOURCE
) -> list[dict[str, Any]]:
    """Controlled-mutation case records (with snapshots) for every PASS snapshot given.

    At most ``max_per_source`` mutants per PR, test-file removals first (the clearest unmet
    requirement), then by path, so the choice is deterministic.
    """
    out = []
    for case_id, case in sorted(snapshots.items()):
        if case.get("expected_verdict") != "PASS":
            continue
        mutants = sorted(
            mutate_drop_named_file(case["production_snapshot"]),
            key=lambda m: (not _is_test_path(m["mutation_path"]), m["mutation_path"]),
        )[:max_per_source]
        for index, mutant in enumerate(mutants):
            out.append(
                {
                    "case_id": f"{case_id}-mut-drop{index + 1}",
                    "repo": case["repo"],
                    "pr": case["pr"],
                    "expected_verdict": "NON_PASS",
                    "category": "missing-acceptance-criterion",
                    "provenance": "controlled-mutation",
                    "source_case_id": case_id,
                    "production_snapshot": mutant,
                }
            )
    return out


def generate(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    """Mutants for every PASS screen case, as corpus-ready case records plus their snapshots."""
    screen = {c["case_id"]: c for c in corpus.get("screen_cases", [])}
    return generate_from_snapshots(screen)


def materialize_mutant(source_case: dict[str, Any], path: str) -> dict[str, Any]:
    """Rebuild one mutant snapshot from its source case and the dropped path (deterministic)."""
    matches = [
        m
        for m in mutate_drop_named_file(source_case["production_snapshot"])
        if m["mutation_path"] == path
    ]
    if len(matches) != 1:
        raise ValueError(f"cannot reproduce the {MUTATION} mutant for {path}")
    return matches[0]


def load_case(case: dict[str, Any], root: Path = Path(".")) -> dict[str, Any]:
    """The full case (with production_snapshot) for a corpus case that has a snapshot reference.

    Real cases read their gzip snapshot; controlled-mutation cases are re-derived from the source
    snapshot and the recorded path, so mutants cost no storage and cannot drift from their source.
    """
    recipe = case.get("mutation_recipe")
    if recipe:
        source = load_case({"snapshot_ref": recipe["source_snapshot_ref"]}, root)
        snapshot = materialize_mutant(source, recipe["path"])
        return {
            **{k: v for k, v in case.items() if k != "mutation_recipe"},
            "production_snapshot": snapshot,
        }
    with gzip.open(root / case["snapshot_ref"], "rt") as handle:
        return json.load(handle)


def write_corpus(
    corpus_path: Path,
    snapshot_dir: Path,
    sources: dict[str, dict[str, Any]],
    mutants: list[dict[str, Any]],
) -> tuple[int, int]:
    """Write source snapshots (gzip) and append deduplicated case records to the corpus.

    Real PASS snapshots get ``snapshot_ref`` on their existing corpus case. Mutant cases are appended
    as recipes (``mutation_recipe``: source case, snapshot reference and dropped path) with
    ``provenance: controlled-mutation``; their snapshots are re-derived on load. Re-running adds
    nothing that already exists. Returns (sources_referenced, mutants_added).
    """
    corpus = json.loads(corpus_path.read_text())
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    existing = {case["case_id"]: case for case in corpus["cases"]}
    refs: dict[str, str] = {}
    referenced = added = 0
    for case_id, case in sources.items():
        ref = f"{snapshot_dir.as_posix()}/{case_id}.json.gz"
        refs[case_id] = ref
        with gzip.open(snapshot_dir / f"{case_id}.json.gz", "wt", compresslevel=9) as handle:
            json.dump(case, handle, sort_keys=True)
        if existing[case_id].get("snapshot_ref") != ref:
            existing[case_id]["snapshot_ref"] = ref
            referenced += 1
    for case in mutants:
        if case["case_id"] in existing:
            continue
        record = {k: v for k, v in case.items() if k != "production_snapshot"}
        record["mutation_recipe"] = {
            "source_case_id": case["source_case_id"],
            "source_snapshot_ref": refs.get(
                case["source_case_id"], existing[case["source_case_id"]].get("snapshot_ref")
            ),
            "mutation": MUTATION,
            "path": case["production_snapshot"]["mutation_path"],
        }
        corpus["cases"].append(record)
        existing[case["case_id"]] = record
        added += 1
    corpus["mutation_generation"] = {
        "tool": "tools/generate_mutation_cases.py",
        "mutation": MUTATION,
        "note": "Controlled-mutation cases are machine ground truth; see approval_stage.controlled_mutation.",
    }
    corpus_path.write_text(json.dumps(corpus, indent=2) + "\n")
    return referenced, added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("config/model_eval_pilot.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--artifacts",
        nargs="*",
        type=Path,
        default=[],
        help="MAINT-78 capture artifact directories (each holds captured-inputs/case-N)",
    )
    parser.add_argument("--write", action="store_true", help="append to the corpus and snapshots")
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--max-per-source", type=int, default=MAX_PER_SOURCE)
    args = parser.parse_args(argv)
    corpus = json.loads(args.corpus.read_text())
    sources = snapshots_from_artifacts(corpus, args.artifacts) if args.artifacts else {}
    cases = generate_from_snapshots(sources, args.max_per_source) if sources else generate(corpus)
    if args.write:
        referenced, added = write_corpus(args.corpus, args.snapshot_dir, sources, cases)
        print(
            f"wrote {len(sources)} source snapshot(s) ({referenced} newly referenced), {added} new mutant case(s)"
        )
    print(f"generated {len(cases)} controlled-mutation case(s)")
    for case in cases:
        print(" ", case["case_id"], "<-", case["source_case_id"])
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
