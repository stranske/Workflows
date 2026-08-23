"""Static guard: a runner artifact must not be committable, and this enforces the checklist.

Background — why this test exists
=================================
`docs/WORKFLOW_ARTIFACT_CHECKLIST.md` already says all of this. Its decision tree ends at
"auto-generated → use workflow artifacts instead, add to .gitignore", and it carries a "Recovery
from Artifact Pollution" procedure. But **nothing referenced or enforced it** — a grep across
`.yml`, `.py` and `.sh` found zero callers — so it was a document, not a gate, and the gate is what
was missing.

What went wrong without it. `reusable-codex-run.yml` gained a "Write worker model attempt artifact"
step that wrote `langsmith-fleet-worker-attempt.json` into the **checkout root**, purely to stage
the `actions/upload-artifact` step on the next line. The commit step earlier in the same job runs
`git add -A` and then subtracts a hand-curated `git reset HEAD --` list, so an artifact absent from
that list is committed onto whatever PR happens to be open. This one was absent. PR #2856
(2026-07-31) diagnosed it exactly — "while tracked, every run that rewrote it produced a diff that
codex-autofix then committed onto whatever PR happened to be open" — and fixed **this repo only**,
never `templates/consumer-repo/.gitignore`. Six consumer repos were still carrying a tracked copy on
2026-08-23 (Travel-Plan-Permission, Counter_Risk, Pension-Data, Ready, trip-planner, Orchestrator),
and in stranske/Orchestrator it produced an add/add merge conflict on a path neither side authored.

The mechanic that decides the fix, verified against a scratch repository: `git add -A` **skips** an
ignored *untracked* path but **stages** an ignored *tracked* one. So ignoring is not untracking, and
the `git reset HEAD --` list is only load-bearing for paths already in the index. Writing outside the
checkout beats both — it removes the class instead of adding entry N+1 to a list somebody must
remember.

What is asserted
================
1.  The worker-attempt artifact is written to and uploaded from `RUNNER_TEMP`, never the checkout.
2.  Its emitter heredoc still compiles (it is YAML text, so nothing else would catch a syntax error
    until runtime — the same gap `test_reusable_run_refpack_heredoc_compiles.py` exists to close).
3.  **The general rule:** every `actions/upload-artifact` path in the reusable runner workflows is
    either outside the checkout, or covered by the commit step's exclusion list, or covered by the
    consumer-template `.gitignore` — otherwise it must be named in `KNOWN_IN_CHECKOUT` with a
    reason. That is the checklist, as a gate. A new artifact step now fails here instead of
    surfacing weeks later as a merge conflict in a consumer repo.
"""

from __future__ import annotations

import fnmatch
import re
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

REUSABLE_RUN_WORKFLOWS = (
    ".github/workflows/reusable-codex-run.yml",
    ".github/workflows/reusable-claude-run.yml",
)
CODEX_RUN = ".github/workflows/reusable-codex-run.yml"
CONSUMER_TEMPLATE_GITIGNORE = "templates/consumer-repo/.gitignore"

WORKER_ATTEMPT_BASENAME = "langsmith-fleet-worker-attempt.json"

# Artifact paths that ARE inside the checkout and are deliberately not excluded/ignored. Each entry
# is an incident record: say why it is safe, so the next reader can tell a reviewed decision from an
# oversight. Anything not listed here must be excluded, ignored, or written outside the checkout.
KNOWN_IN_CHECKOUT: dict[str, str] = {
    "error-diagnostics/": (
        "Created by the 'Create error diagnostics' step, which runs AFTER the commit step in the "
        "same job, so `git add -A` never sees it. That is step ORDERING, not a safety property: "
        "reorder the steps, or add a second commit step later in the job, and this becomes the "
        "langsmith-fleet-worker-attempt.json defect again. Prefer moving it under RUNNER_TEMP if it "
        "is ever touched."
    ),
}


def workflow_text(rel: str) -> str:
    path = ROOT / rel
    assert path.is_file(), f"missing workflow file: {rel}"
    return path.read_text(encoding="utf-8")


def upload_artifact_paths(rel: str) -> list[str]:
    """Every `path:` given to actions/upload-artifact, read from the PARSED yaml.

    Parsed rather than grepped on purpose: `path:` accepts a block scalar listing several globs, and
    a regex over the raw text silently sees only the first line of one. A gate with a parser that
    quietly under-reports is worse than no gate.
    """
    doc = yaml.safe_load(workflow_text(rel))
    found: list[str] = []
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            uses = str(step.get("uses") or "")
            if not uses.startswith("actions/upload-artifact"):
                continue
            raw = (step.get("with") or {}).get("path")
            if raw is None:
                continue
            for line in str(raw).splitlines():
                entry = line.strip()
                if entry:
                    found.append(entry)
    return found


def commit_step_exclusions() -> list[str]:
    """The `git reset HEAD --` denylist the commit step subtracts from `git add -A`."""
    match = re.search(r"git reset HEAD -- \\\n(.*?)\n\s*2>/dev/null", workflow_text(CODEX_RUN), re.S)
    assert match, (
        "could not locate the commit step's `git reset HEAD --` exclusion list in "
        f"{CODEX_RUN}; this guard can no longer tell which artifacts are excluded"
    )
    return [
        line.strip().rstrip("\\").strip()
        for line in match.group(1).splitlines()
        if line.strip() and line.strip() != "\\"
    ]


def template_ignore_patterns() -> list[str]:
    text = (ROOT / CONSUMER_TEMPLATE_GITIGNORE).read_text(encoding="utf-8")
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def covered_by(path: str, patterns: list[str]) -> bool:
    """Is `path` matched by any pattern? Compared both ways, since either side may carry the glob."""
    bare = path.rstrip("/")
    for pattern in patterns:
        pat = pattern.lstrip("/").rstrip("/")
        if not pat or pattern.startswith("!"):
            continue
        if fnmatch.fnmatch(bare, pat) or fnmatch.fnmatch(pat, bare):
            return True
    return False


def outside_checkout(path: str) -> bool:
    """Runner-temp and absolute paths are not in the working tree, so git can never stage them."""
    lowered = path.lower()
    return (
        path.startswith("/")
        or "runner.temp" in lowered
        or "runner_temp" in lowered
        or "${{ env.runner_temp }}" in lowered
    )


def test_worker_attempt_artifact_is_written_outside_the_checkout():
    text = workflow_text(CODEX_RUN)
    assert f'open("{WORKER_ATTEMPT_BASENAME}"' not in text, (
        f"{CODEX_RUN} writes {WORKER_ATTEMPT_BASENAME} into the checkout root again. The commit step "
        "runs `git add -A` and subtracts only a hand-curated list, so this file gets committed onto "
        "whatever PR is open and then collides with the copy the previous merge left on main — the "
        "PR #2856 defect, which reached six consumer repos. Write it under RUNNER_TEMP; the "
        "upload-artifact step accepts any path."
    )
    assert "RUNNER_TEMP" in text, f"{CODEX_RUN} no longer stages the worker attempt under RUNNER_TEMP"


def test_worker_attempt_artifact_is_uploaded_from_outside_the_checkout():
    matches = [p for p in upload_artifact_paths(CODEX_RUN) if WORKER_ATTEMPT_BASENAME in p]
    assert matches, f"{CODEX_RUN} no longer uploads {WORKER_ATTEMPT_BASENAME}"
    for path in matches:
        assert outside_checkout(path), (
            f"{CODEX_RUN} uploads {path!r} from inside the checkout. Uploading is the whole reason "
            "the file exists, so it never needs to be in the working tree at all."
        )


def test_worker_attempt_emitter_heredoc_compiles():
    text = workflow_text(CODEX_RUN)
    match = re.search(
        r"- name: Write worker model attempt artifact.*?python - <<'PY'\n(.*?)\n          PY\n",
        text,
        re.S,
    )
    assert match, f"{CODEX_RUN}: could not locate the worker-attempt emitter heredoc"
    body = textwrap.dedent(match.group(1))
    try:
        compile(body, f"<{CODEX_RUN}:worker-attempt>", "exec")
    except SyntaxError as exc:  # IndentationError is a SyntaxError subclass
        pytest.fail(
            f"{CODEX_RUN}: worker-attempt emitter heredoc does not compile: "
            f"{type(exc).__name__}: {exc}"
        )


@pytest.mark.parametrize("workflow_rel", REUSABLE_RUN_WORKFLOWS)
def test_every_uploaded_artifact_is_uncommittable(workflow_rel: str):
    """The checklist, as a gate: an artifact step may not leave a committable file behind."""
    exclusions = commit_step_exclusions()
    ignores = template_ignore_patterns()

    offenders = []
    for path in sorted(set(upload_artifact_paths(workflow_rel))):
        if outside_checkout(path) or path in KNOWN_IN_CHECKOUT:
            continue
        if covered_by(path, exclusions) or covered_by(path, ignores):
            continue
        offenders.append(path)

    assert not offenders, (
        f"{workflow_rel} uploads artifact path(s) {offenders} that live in the checkout and are "
        "neither excluded by the commit step's `git reset HEAD --` list nor ignored by "
        f"{CONSUMER_TEMPLATE_GITIGNORE}. `git add -A` will commit them onto whatever PR is open, and "
        "the next PR then conflicts with the copy the last merge left on main — that is exactly how "
        f"{WORKER_ATTEMPT_BASENAME} reached six consumer repos. Pick one: write it under "
        "RUNNER_TEMP (best — removes the class), add it to the template .gitignore (and untrack it "
        "everywhere, since ignoring does not untrack), or record it in KNOWN_IN_CHECKOUT with a "
        "reason saying why it is safe."
    )


def test_known_in_checkout_entries_state_a_reason():
    """An allowlist without reasons decays into a list of things nobody dares remove."""
    for path, reason in KNOWN_IN_CHECKOUT.items():
        assert len(reason) > 80, f"KNOWN_IN_CHECKOUT[{path!r}] needs a real reason, not a label"


def test_known_in_checkout_has_no_stale_entries():
    """An allowlisted path that is no longer uploaded anywhere must be deleted, not carried."""
    uploaded = {
        path for rel in REUSABLE_RUN_WORKFLOWS for path in upload_artifact_paths(rel)
    }
    stale = sorted(set(KNOWN_IN_CHECKOUT) - uploaded)
    assert not stale, (
        f"KNOWN_IN_CHECKOUT names {stale}, which no upload-artifact step references any more. "
        "Remove the entry — a stale allowlist entry silently widens the gate."
    )
