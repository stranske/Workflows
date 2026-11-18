import pathlib

WORKFLOW = pathlib.Path("templates/consumer-repo/.github/workflows/maint-76-claude-code-review.yml")


def test_dispatch_pr_number_read_from_event_payload_not_action_input():
    # workflow_dispatch inputs live in context.payload.inputs; core.getInput reads
    # INPUT_* env vars that actions/github-script only sets from its own `with:`.
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count("context.payload.inputs") == 1
    assert source.count('core.getInput("pr_number")') == 0
