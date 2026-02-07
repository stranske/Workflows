import pytest

from tests._autofix_diag import DiagnosticsRecorder, autofix_recorder  # noqa: F401


@pytest.fixture
def llm_env_sentinel(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {
        "GITHUB_REPOSITORY": "sentinel/repo",
        "GITHUB_RUN_ID": "run-777",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def llm_metadata_sentinel(llm_env_sentinel: dict[str, str]):
    def _build(
        *,
        operation: str,
        pr_number: int | str | None = None,
        issue_number: int | str | None = None,
        issue_or_pr_number: int | str | None = None,
    ) -> dict[str, object]:
        if issue_or_pr_number is None:
            if pr_number is not None:
                issue_or_pr_number = pr_number
            elif issue_number is not None:
                issue_or_pr_number = issue_number
            else:
                issue_or_pr_number = "unknown"
        return {
            "repo": llm_env_sentinel["GITHUB_REPOSITORY"],
            "run_id": llm_env_sentinel["GITHUB_RUN_ID"],
            "issue_or_pr_number": str(issue_or_pr_number),
            "operation": operation,
            "pr_number": str(pr_number) if pr_number is not None else None,
            "issue_number": str(issue_number) if issue_number is not None else None,
        }

    return _build


@pytest.fixture
def llm_config_sentinel(
    llm_env_sentinel: dict[str, str],
    llm_metadata_sentinel,
):
    def _build(
        *,
        operation: str,
        pr_number: int | str | None = None,
        issue_number: int | str | None = None,
        issue_or_pr_number: int | str | None = None,
    ) -> dict[str, object]:
        metadata = llm_metadata_sentinel(
            operation=operation,
            pr_number=pr_number,
            issue_number=issue_number,
            issue_or_pr_number=issue_or_pr_number,
        )
        tags = [
            "workflows-agents",
            f"operation:{operation}",
            f"repo:{llm_env_sentinel['GITHUB_REPOSITORY']}",
            f"issue_or_pr:{metadata['issue_or_pr_number']}",
            f"run_id:{llm_env_sentinel['GITHUB_RUN_ID']}",
        ]
        return {"metadata": metadata, "tags": tags}

    return _build


@pytest.fixture
def llm_typeerror_client_factory():
    class TypeErrorClient:
        def __init__(self, response: object, message: str = "bad config") -> None:
            self.response = response
            self.message = message
            self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.fail_first = True

        def invoke(self, *args: object, **kwargs: object) -> object:
            self.calls.append((args, dict(kwargs)))
            if self.fail_first:
                self.fail_first = False
                raise TypeError(self.message)
            return self.response

    return TypeErrorClient
