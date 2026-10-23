from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools import generate_mutation_cases as g

ROOT = Path(__file__).resolve().parents[2]


def _context(requirement: str, scope: str = "Context mentions src/other.py only.") -> str:
    return f"""# Verifier context

## CI Information

**Note:** This verification runs post-merge. The CI results below confirm which test suites ran on the merge commit; a CI workflow concluding `failure` disqualifies a PASS verdict.

| Workflow | Conclusion | Run | Jobs (summary) |
| --- | --- | --- | --- |
| pr-00-gate.yml | success | [run](https://example.test/runs/1) | success: 3<br>samples: lint (success) |
| selftest.yml | success | [run](https://example.test/runs/2) | success: 1<br>samples: tests (success) |

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
new file mode 100644
--- /dev/null
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
    assert {c["category"] for c in cases} == {
        "missing-acceptance-criterion",
        "ci-failure-disqualifier",
    }
    assert {c["source_case_id"] for c in cases} == {"c1"}  # never mutates an already-NON_PASS case


def test_real_captured_snapshots_are_handled_in_their_real_format():
    corpus = json.loads((ROOT / "config/model_eval_pilot.json").read_text())
    by_id = {c["case_id"]: c for c in corpus["screen_cases"]}
    snapshot = by_id["fineart-755-missing-proof"]["production_snapshot"]
    mutants = g.mutate_drop_named_file(snapshot)
    # the test file is MODIFIED (not new) and only named in an acceptance run command, so it may
    # already satisfy the requirement from the base commit: only the Tasks-named source change drops
    assert {m["mutation_note"].split("`")[1] for m in mutants} == {
        "src/fine_art_archive/known_works/fetchers.py",
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
    for case in (c for c in mutants if c["production_snapshot"]["mutation"] == g.MUTATION):
        mutant = case["production_snapshot"]
        dropped = mutant["mutation_path"]
        assert f"b/{dropped}" not in mutant["diff"] and f"b/{dropped}" in snapshot["diff"]
        assert g.validate(snapshot, mutant, dropped)
    ci = [c for c in mutants if c["production_snapshot"]["mutation"] == g.MUTATION_CI]
    assert len(ci) == 1 and ci[0]["production_snapshot"]["diff"] == snapshot["diff"]


def test_only_generated_ci_mutants_are_diagnostic_only(tmp_path):
    corpus = json.loads(_corpus(tmp_path).read_text())
    sources = g.snapshots_from_artifacts(corpus, [_artifact(tmp_path)])
    mutants = g.generate_from_snapshots(sources)
    ci = [case for case in mutants if case["category"] == g.CATEGORY_CI]
    drops = [case for case in mutants if case["category"] == g.CATEGORY_DROP]
    assert ci and drops
    assert all(case["diagnostic_only"] is True for case in ci)
    assert all("diagnostic_only" not in case for case in drops)


def test_a_captured_pr_that_is_not_a_pass_corpus_case_is_skipped(tmp_path):
    corpus = json.loads(_corpus(tmp_path).read_text())  # PR 99 is the NON_PASS case
    assert g.snapshots_from_artifacts(corpus, [_artifact(tmp_path, pr=99)]) == {}
    assert g.snapshots_from_artifacts(corpus, [_artifact(tmp_path, repo="x/y", pr=7)]) == {}


def test_mutants_per_source_are_capped_tests_first(tmp_path):
    sources = g.snapshots_from_artifacts(
        json.loads(_corpus(tmp_path).read_text()), [_artifact(tmp_path)]
    )
    capped = g.generate_from_snapshots(sources, max_per_source=1)
    drops = [c for c in capped if c["production_snapshot"]["mutation"] == g.MUTATION]
    assert len(drops) == 1  # the fail-ci mutant is separate: one per PR whatever the drop cap
    assert drops[0]["production_snapshot"]["mutation_path"] == "tests/test_feature.py"


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


def test_a_modified_file_named_only_in_an_acceptance_run_command_is_never_dropped():
    snap = _snapshot()
    ctx = (
        snap["context"]
        .replace(
            "--- /dev/null\n+++ b/tests/test_feature.py",
            "--- a/tests/test_feature.py\n+++ b/tests/test_feature.py",
        )
        .replace("new file mode 100644\n", "")
    )
    dropped = {m["mutation_note"].split("`")[1] for m in g.mutate_drop_named_file({"context": ctx})}
    assert "tests/test_feature.py" not in dropped  # modified, so it existed before the change


def test_a_modified_source_file_needs_a_tasks_line_with_a_change_verb():
    ctx = _context("It works.").replace(
        "Implement `src/feature.py` as described.", "See `src/feature.py` for background."
    )
    dropped = {m["mutation_note"].split("`")[1] for m in g.mutate_drop_named_file({"context": ctx})}
    assert "src/feature.py" not in dropped


def test_a_newly_added_file_named_in_acceptance_is_dropped():
    dropped = {m["mutation_note"].split("`")[1] for m in g.mutate_drop_named_file(_snapshot())}
    assert "tests/test_feature.py" in dropped


def test_fail_ci_flips_exactly_one_row_and_keeps_everything_else():
    snap = _snapshot()
    (mutant,) = g.mutate_fail_ci(snap)
    before, after = snap["context"].splitlines(), mutant["context"].splitlines()
    changed = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert len(before) == len(after) and len(changed) == 1
    assert (
        "| pr-00-gate.yml | failure |" in changed[0][1]
        and "failure: 1, success: 2" in changed[0][1]
    )
    assert mutant["mutation"] == g.MUTATION_CI and mutant["mutation_path"] == "pr-00-gate.yml"
    assert g.validate_ci(snap, mutant)


def test_fail_ci_is_not_offered_without_the_stated_rule_or_with_a_failure_already():
    snap = _snapshot()
    no_rule = dict(snap, context=snap["context"].replace(g.CI_RULE, "CI is informational"))
    already = dict(
        snap,
        context=snap["context"].replace("| selftest.yml | success |", "| selftest.yml | failure |"),
    )
    no_table = dict(
        snap,
        context=snap["context"].split("| Workflow |")[0]
        + "## Plan sources"
        + snap["context"].split("## Plan sources")[1],
    )
    assert (
        g.mutate_fail_ci(no_rule) == []
        and g.mutate_fail_ci(already) == []
        and g.mutate_fail_ci(no_table) == []
    )


def test_fail_ci_validation_rejects_a_second_changed_line():
    snap = _snapshot()
    (mutant,) = g.mutate_fail_ci(snap)
    tampered = dict(mutant, context=mutant["context"].replace("Implement", "Skip"))
    assert not g.validate_ci(snap, tampered)


def test_fail_ci_works_on_a_real_captured_context_and_round_trips_as_a_recipe():
    corpus = json.loads((ROOT / "config/model_eval_pilot.json").read_text())
    case = next(c for c in corpus["screen_cases"] if c["case_id"] == "wf-3676-evidence-pass")
    snapshot = case["production_snapshot"]
    (mutant,) = g.mutate_fail_ci(snapshot)
    assert mutant["mutation_path"] == "pr-00-gate.yml" and g.validate_ci(snapshot, mutant)
    rebuilt = g.materialize_mutant(case, "pr-00-gate.yml", g.MUTATION_CI)
    assert rebuilt["context"] == mutant["context"]


@pytest.fixture
def evaluable(monkeypatch):
    monkeypatch.setattr(g, "coverage_sufficient", lambda snapshot: True)


def test_mutants_from_an_insufficient_input_never_enter_the_corpus(monkeypatch):
    corpus = {
        "screen_cases": [
            {
                "case_id": "c1",
                "repo": "o/r",
                "pr": 1,
                "expected_verdict": "PASS",
                "production_snapshot": _snapshot(),
            }
        ]
    }
    monkeypatch.setattr(g, "coverage_sufficient", lambda snapshot: False)
    assert g.generate(corpus) == []
    monkeypatch.setattr(g, "coverage_sufficient", lambda snapshot: True)
    assert g.generate(corpus)


def test_coverage_check_is_the_verifiers_own_and_real_captures_are_mostly_insufficient():
    corpus = json.loads((ROOT / "config/model_eval_pilot.json").read_text())
    by_id = {c["case_id"]: c for c in corpus["screen_cases"]}
    assert g.coverage_sufficient(by_id["wf-3676-evidence-pass"]["production_snapshot"]) is True
    assert g.coverage_sufficient(by_id["wf-3668-evidence-pass"]["production_snapshot"]) is False
    assert g.coverage_sufficient({"context": "no chain depth"}) is False  # malformed never counts


def test_rebuild_replaces_earlier_generated_cases_and_files(tmp_path, evaluable):
    corpus_path = _corpus(tmp_path)
    snapshot_dir = tmp_path / "snaps"
    sources = g.snapshots_from_artifacts(json.loads(corpus_path.read_text()), [_artifact(tmp_path)])
    mutants = g.generate_from_snapshots(sources)
    g.write_corpus(corpus_path, snapshot_dir, sources, mutants)
    (snapshot_dir / "stale.json.gz").write_bytes(b"x")
    corpus = json.loads(corpus_path.read_text())
    corpus["cases"].append(
        {"case_id": "old-mut", "provenance": "controlled-mutation", "expected_verdict": "NON_PASS"}
    )
    corpus_path.write_text(json.dumps(corpus))
    g.write_corpus(corpus_path, snapshot_dir, sources, mutants[:1], rebuild=True)
    after = json.loads(corpus_path.read_text())["cases"]
    ids = {c["case_id"] for c in after}
    assert "old-mut" not in ids and not (snapshot_dir / "stale.json.gz").exists()
    assert sum(c.get("provenance") == "controlled-mutation" for c in after) == 1


def test_a_mutant_record_is_never_mistaken_for_its_sources_corpus_case(tmp_path, evaluable):
    corpus = json.loads(_corpus(tmp_path).read_text())
    corpus["cases"].append(
        {
            "case_id": "case-7-mut-drop1",
            "repo": "o/r",
            "pr": "7",
            "provenance": "controlled-mutation",
            "expected_verdict": "NON_PASS",
        }
    )
    assert g.corpus_case_for(corpus, "o/r", 7)["case_id"] == "case-7"
    assert list(g.snapshots_from_artifacts(corpus, [_artifact(tmp_path)])) == ["case-7"]
