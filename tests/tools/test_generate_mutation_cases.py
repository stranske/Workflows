from __future__ import annotations

import json
from pathlib import Path

from tools import generate_mutation_cases as g

ROOT = Path(__file__).resolve().parents[2]


def _context(requirement: str, scope: str = "Context mentions src/other.py only.") -> str:
    return f"""# Verifier context

## Plan sources (scope, tasks, acceptance)

#### Scope
{scope}

#### Tasks
- [ ] Implement `src/feature.py` as described.

#### Acceptance Criteria
- [ ] {requirement}

## PR Diff Summary

- Files changed: 3
- Total additions: 30
- Total deletions: 2

### File changes
- src/feature.py (+10/-2)
- tests/test_feature.py (+12/-0)
- docs/note.md (+8/-0)

## PR Diff (full)

```diff
diff --git a/src/feature.py b/src/feature.py
--- a/src/feature.py
+++ b/src/feature.py
@@ -1 +1 @@
-old
+new
diff --git a/tests/test_feature.py b/tests/test_feature.py
--- a/tests/test_feature.py
+++ b/tests/test_feature.py
@@ -0,0 +1 @@
+def test_feature_behaves():
diff --git a/docs/note.md b/docs/note.md
--- a/docs/note.md
+++ b/docs/note.md
@@ -0,0 +1 @@
+note
```
"""


def _snapshot(requirement="`pytest tests/test_feature.py -k test_feature_behaves` passes."):
    return {"context": _context(requirement), "diff_summary": "", "pr": 1}


def test_only_files_named_in_tasks_or_acceptance_are_dropped():
    mutants = g.mutate_drop_named_file(_snapshot())
    dropped = sorted(m["mutation_note"].split("`")[1] for m in mutants)
    assert dropped == ["src/feature.py", "tests/test_feature.py"]  # docs/note.md is not required


def test_a_file_that_only_scope_mentions_is_never_dropped():
    snap = {"context": _context("It works.", scope="See docs/note.md for background."), "pr": 1}
    dropped = {m["mutation_note"].split("`")[1] for m in g.mutate_drop_named_file(snap)}
    assert "docs/note.md" not in dropped


def test_mutant_keeps_the_requirement_text_and_agrees_with_its_own_summary():
    snap = _snapshot()
    for mutant in g.mutate_drop_named_file(snap):
        assert g.validate(snap, mutant, mutant["mutation_note"].split("`")[1])
        before, after = g.split_context(snap["context"]), g.split_context(mutant["context"])
        assert before[0] == after[0]  # plan text untouched
        assert mutant["input_kind"] == "controlled_defect" and mutant["mutation"] == g.MUTATION
        assert mutant["context"].rstrip().endswith("```")


def test_summary_totals_follow_the_removed_file():
    snap = _snapshot()
    tests_mutant = next(
        m for m in g.mutate_drop_named_file(snap) if "tests/test_feature.py" in m["mutation_note"]
    )
    summary = tests_mutant["context"]
    assert "- Files changed: 2" in summary and "- Total additions: 18" in summary
    assert "- tests/test_feature.py" not in summary.split("## PR Diff (full)")[0]


def test_single_file_prs_have_nothing_to_drop():
    ctx = _context("x").split("diff --git a/tests")[0] + "```\n"
    ctx = ctx.replace("- tests/test_feature.py (+12/-0)\n", "").replace(
        "- docs/note.md (+8/-0)\n", ""
    )
    assert g.mutate_drop_named_file({"context": ctx}) == []


def test_validation_rejects_an_unchanged_or_plan_altering_mutant():
    snap = _snapshot()
    assert not g.validate(snap, dict(snap), "src/feature.py")
    altered = dict(snap, context=snap["context"].replace("Implement", "Skip"))
    assert not g.validate(snap, altered, "src/feature.py")


def test_generate_labels_cases_as_controlled_mutation_non_pass():
    corpus = {
        "screen_cases": [
            {
                "case_id": "c1",
                "repo": "o/r",
                "pr": 1,
                "expected_verdict": "PASS",
                "production_snapshot": _snapshot(),
            },
            {
                "case_id": "c2",
                "repo": "o/r",
                "pr": 2,
                "expected_verdict": "NON_PASS",
                "production_snapshot": _snapshot(),
            },
        ]
    }
    cases = g.generate(corpus)
    assert cases and all(c["expected_verdict"] == "NON_PASS" for c in cases)
    assert all(c["provenance"] == "controlled-mutation" for c in cases)
    assert all(c["category"] == "missing-acceptance-criterion" for c in cases)
    assert {c["source_case_id"] for c in cases} == {"c1"}  # never mutates an already-NON_PASS case


def test_real_captured_snapshots_are_handled_in_their_real_format():
    corpus = json.loads((ROOT / "config/model_eval_pilot.json").read_text())
    by_id = {c["case_id"]: c for c in corpus["screen_cases"]}
    snapshot = by_id["fineart-755-missing-proof"]["production_snapshot"]
    mutants = g.mutate_drop_named_file(snapshot)
    assert {m["mutation_note"].split("`")[1] for m in mutants} == {
        "src/fine_art_archive/known_works/fetchers.py",
        "tests/test_known_works_fetchers.py",
    }
    for mutant in mutants:
        assert g.validate(snapshot, mutant, mutant["mutation_note"].split("`")[1])
