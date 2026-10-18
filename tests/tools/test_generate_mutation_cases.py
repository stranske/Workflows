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


def _artifact(tmp_path: Path, repo="o/r", pr=7) -> Path:
    """A MAINT-78 capture artifact: captured-inputs/case-1 with consistent hashes."""
    import hashlib

    root = tmp_path / f"artifact-{repo.replace('/', '_')}-{pr}"
    case = root / "captured-inputs" / "case-1"
    case.mkdir(parents=True)
    context = _context("`pytest tests/test_feature.py -k test_feature_behaves` passes.")
    patch = context.split("```diff\n")[1].rsplit("```", 1)[0]
    summary = context.split("## PR Diff Summary")[1].split("## PR Diff (full)")[0]
    summary = "## PR Diff Summary" + summary
    (case / "verifier-context.md").write_text(context)
    (case / "verifier-diff-summary.md").write_text(summary)
    (case / "verifier-pr-diff.patch").write_text(patch)
    sha = lambda text: hashlib.sha256(text.encode()).hexdigest()  # noqa: E731
    (case / "verifier-input-manifest.json").write_text(
        json.dumps(
            {
                "schema": "workflows-verifier-input-snapshot/v1",
                "capture_kind": "retrospective",
                "repository": repo,
                "pr": pr,
                "merge_sha": "a" * 40,
                "source_run_id": "1",
                "chain_depth": 0,
                "context_sha256": sha(context),
                "diff_summary_sha256": sha(summary),
                "diff_sha256": sha(patch),
            }
        )
    )
    return root


def _corpus(tmp_path: Path, repo="o/r", pr=7) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case-7",
                        "repo": repo,
                        "pr": str(pr),
                        "expected_verdict": "PASS",
                        "category": "clean-pass",
                    },
                    {
                        "case_id": "case-8",
                        "repo": repo,
                        "pr": "99",
                        "expected_verdict": "NON_PASS",
                        "category": "follow-up-required",
                    },
                ],
                "screen_cases": [],
            }
        )
    )
    return path


def test_captured_artifacts_become_pass_snapshots_and_mutants_edit_the_separate_diff(tmp_path):
    corpus_path = _corpus(tmp_path)
    corpus = json.loads(corpus_path.read_text())
    sources = g.snapshots_from_artifacts(corpus, [_artifact(tmp_path)])
    assert list(sources) == ["case-7"]
    snapshot = sources["case-7"]["production_snapshot"]
    assert (
        snapshot["diff"].startswith("diff --git")
        and snapshot["input_kind"] == "retrospective_capture"
    )
    mutants = g.generate_from_snapshots(sources)
    assert mutants
    for case in mutants:
        mutant = case["production_snapshot"]
        dropped = mutant["mutation_path"]
        assert f"b/{dropped}" not in mutant["diff"] and f"b/{dropped}" in snapshot["diff"]
        assert g.validate(snapshot, mutant, dropped)


def test_a_captured_pr_that_is_not_a_pass_corpus_case_is_skipped(tmp_path):
    corpus = json.loads(_corpus(tmp_path).read_text())  # PR 99 is the NON_PASS case
    assert g.snapshots_from_artifacts(corpus, [_artifact(tmp_path, pr=99)]) == {}
    assert g.snapshots_from_artifacts(corpus, [_artifact(tmp_path, repo="x/y", pr=7)]) == {}


def test_mutants_per_source_are_capped_tests_first(tmp_path):
    sources = g.snapshots_from_artifacts(
        json.loads(_corpus(tmp_path).read_text()), [_artifact(tmp_path)]
    )
    assert len(g.generate_from_snapshots(sources, max_per_source=1)) == 1
    first = g.generate_from_snapshots(sources, max_per_source=1)[0]
    assert first["production_snapshot"]["mutation_path"] == "tests/test_feature.py"


def test_write_appends_deduplicated_recipes_and_loading_rederives_the_mutants(tmp_path):
    corpus_path = _corpus(tmp_path)
    snapshot_dir = tmp_path / "snaps"
    sources = g.snapshots_from_artifacts(json.loads(corpus_path.read_text()), [_artifact(tmp_path)])
    mutants = g.generate_from_snapshots(sources)
    first = g.write_corpus(corpus_path, snapshot_dir, sources, mutants)
    second = g.write_corpus(corpus_path, snapshot_dir, sources, mutants)
    corpus = json.loads(corpus_path.read_text())
    ids = [c["case_id"] for c in corpus["cases"]]
    assert first == (1, len(mutants)) and second == (0, 0)
    assert len(ids) == len(set(ids)) == 2 + len(mutants)
    added = [c for c in corpus["cases"] if c.get("provenance") == "controlled-mutation"]
    assert all(
        c["expected_verdict"] == "NON_PASS" and "production_snapshot" not in c for c in added
    )
    assert sorted(p.name for p in snapshot_dir.iterdir()) == [
        "case-7.json.gz"
    ]  # mutants cost no files
    # loading re-derives each mutant exactly as the generator produced it
    for record, original in zip(added, mutants, strict=True):
        loaded = g.load_case(record, tmp_path)
        assert loaded["production_snapshot"] == original["production_snapshot"]
        assert loaded["expected_verdict"] == "NON_PASS"
    real = next(c for c in corpus["cases"] if c["case_id"] == "case-7")
    assert (
        g.load_case(real, tmp_path)["production_snapshot"]
        == sources["case-7"]["production_snapshot"]
    )


def test_quoted_diff_headers_are_parsed_like_unquoted_ones():
    body = (
        'diff --git "a/src/x y.py" "b/src/x y.py"\n--- a\n+++ b\n@@ -1 +1 @@\n-a\n+b\n'
        "diff --git a/tests/t.py b/tests/t.py\n--- a\n+++ b\n@@ -1 +1 @@\n-a\n+b\n"
    )
    assert [p for p, _ in g.diff_blocks(body)] == ["src/x y.py", "tests/t.py"]


def test_unlisted_sources_are_mutated_but_never_become_corpus_cases(tmp_path):
    corpus_path = _corpus(tmp_path)
    corpus = json.loads(corpus_path.read_text())
    artifact = _artifact(tmp_path, repo="o/other", pr=55)  # not in the corpus
    assert g.snapshots_from_artifacts(corpus, [artifact]) == {}
    sources = g.snapshots_from_artifacts(corpus, [artifact], allow_unlisted=True)
    assert list(sources) == ["other-55"] and sources["other-55"]["source_only"] is True
    mutants = g.generate_from_snapshots(sources)
    assert mutants and all(m["source_case_id"] == "other-55" for m in mutants)
    snapshot_dir = tmp_path / "snaps"
    g.write_corpus(corpus_path, snapshot_dir, sources, mutants)
    written = json.loads(corpus_path.read_text())["cases"]
    assert "other-55" not in {c["case_id"] for c in written}  # the source is not a corpus case
    added = [c for c in written if c.get("provenance") == "controlled-mutation"]
    assert added and (snapshot_dir / "other-55.json.gz").exists()
    for record in added:  # recipes still load: the source snapshot file is found by reference
        assert g.load_case(record, tmp_path)["expected_verdict"] == "NON_PASS"
