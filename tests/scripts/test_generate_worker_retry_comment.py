import textwrap
from pathlib import Path

from scripts import generate_worker_retry_comment as generator


def _write_workflow(tmp_path: Path, content: str) -> Path:
    workflow_path = tmp_path / "workflow.yml"
    workflow_path.write_text(textwrap.dedent(content), encoding="utf-8")
    return workflow_path


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

    assert "Label: needs-human" in comment
    assert "Unwrapped github.rest.* call sites:" in comment
    assert "- Step One line 1" in comment
    assert "github.paginate call sites to replace:" in comment
    assert "- Step One line 6" in comment
