from __future__ import annotations

import textwrap
from pathlib import Path

from scripts import generate_worker_retry_comment as generator


def _write_workflow(tmp_path: Path, content: str) -> Path:
    workflow_path = tmp_path / "workflow.yml"
    workflow_path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return workflow_path


COMMENT_HEADER = (
    "Blocked by workflow protection: update .github/workflows/agents-72-codex-belt-worker.yml "
    "to wrap github.rest.* calls with withRetry() and replace github.paginate(...) with "
    "paginateWithRetry(...). Use createTokenAwareRetry() from "
    "./.github/scripts/github-api-with-retry.js for retry + token-rotation."
)


def test_iter_job_scripts_reads_multiple_jobs_and_script_sources(tmp_path: Path) -> None:
    workflow_path = _write_workflow(
        tmp_path,
        """
        name: Example
        on: workflow_dispatch
        jobs:
          run_job:
            runs-on: ubuntu-latest
            steps:
              - name: Run Step
                run: |
                  console.log("run");
          script_job:
            runs-on: ubuntu-latest
            steps:
              - name: Script Step
                uses: actions/github-script@v7
                with:
                  script: |
                    console.log("script");
        """,
    )

    workflow = generator._load_workflow(workflow_path)
    scripts = generator._iter_job_scripts(workflow)

    assert [step_name for step_name, _script in scripts] == ["Run Step", "Script Step"]
    assert [script.strip() for _step_name, script in scripts] == [
        'console.log("run");',
        'console.log("script");',
    ]


def test_detect_retry_loops_preserves_retry_window_behavior() -> None:
    script = textwrap.dedent("""\
        const issue = await github.rest.issues.get({});
        const pull = await withRetry(() => github.rest.pulls.get({}));
        const review = await github.rest.pulls.listReviews({});
        """)

    assert generator._detect_retry_loops(script, "Retry Step") == ["Retry Step line 1"]


def test_paginate_usages_reports_multiple_commands() -> None:
    script = textwrap.dedent("""\
        const issues = await withRetry(() => github.paginate(github.rest.issues.listForRepo, {}));
        const pulls = await withRetry(() => github.paginate(github.rest.pulls.list, {}));
        """)

    assert generator._paginate_usages(script, "Paginate Step") == [
        "Paginate Step line 1",
        "Paginate Step line 2",
    ]


def test_build_comment_scans_multiple_jobs(tmp_path: Path) -> None:
    workflow_path = _write_workflow(
        tmp_path,
        """
        name: Example
        on: workflow_dispatch
        jobs:
          first:
            runs-on: ubuntu-latest
            steps:
              - name: First Job
                run: github.rest.issues.get({})
          second:
            runs-on: ubuntu-latest
            steps:
              - name: Second Job
                run: github.rest.pulls.get({})
        """,
    )

    comment = generator.build_comment(workflow_path)

    assert "- First Job line 1" in comment
    assert "- Second Job line 1" in comment


def test_build_comment_includes_label_and_call_sites(tmp_path: Path) -> None:
    workflow_path = _write_workflow(
        tmp_path,
        """
        name: Example
        on: workflow_dispatch
        jobs:
          sample:
            runs-on: ubuntu-latest
            steps:
              - name: Step One
                run: |
                  const issue = await github.rest.issues.get({
                    owner: "octo",
                    repo: "cat",
                    issue_number: 1,
                  });
                  const list = await github.paginate(github.rest.issues.listForRepo, {
                    owner: "octo",
                    repo: "cat",
                  });
        """,
    )

    comment = generator.build_comment(workflow_path, include_label=True)

    assert comment == "\n".join(
        [
            "Label: needs-human",
            COMMENT_HEADER,
            "",
            "Unwrapped github.rest.* call sites:",
            "- Step One line 1",
            "- Step One line 6",
            "",
            "github.paginate call sites to replace:",
            "- Step One line 6",
        ]
    )


def test_build_comment_reports_no_findings(tmp_path: Path) -> None:
    workflow_path = _write_workflow(
        tmp_path,
        """
        name: Example
        on: workflow_dispatch
        jobs:
          sample:
            runs-on: ubuntu-latest
            steps:
              - name: Wrapped Step
                run: |
                  const issue = await withRetry(() => github.rest.issues.get({}));
        """,
    )

    comment = generator.build_comment(workflow_path)

    assert comment == "\n".join(
        [
            COMMENT_HEADER,
            "",
            "No missing retry/pagination wrappers detected.",
        ]
    )
