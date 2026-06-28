from types import SimpleNamespace

from scripts import cleanup_labels


class FakeLabel:
    def __init__(self, name: str, color: str = "ededed", description: str = "") -> None:
        self.name = name
        self.color = color
        self.description = description
        self.deleted = False

    def delete(self) -> None:
        self.deleted = True


class FakeRepo:
    def __init__(self, labels: list[FakeLabel]) -> None:
        self.labels = {label.name: label for label in labels}

    def get_labels(self) -> list[FakeLabel]:
        return list(self.labels.values())

    def get_label(self, name: str) -> FakeLabel:
        return self.labels[name]


class FakeGithub:
    def __init__(self, repo: FakeRepo) -> None:
        self.repo = repo
        self.requested_repos: list[str] = []

    def get_repo(self, repo_name: str) -> FakeRepo:
        self.requested_repos.append(repo_name)
        return self.repo


def test_classify_label_covers_core_categories() -> None:
    assert cleanup_labels.classify_label("agent:codex") == "functional"
    assert cleanup_labels.classify_label("bug") == "informational"
    assert cleanup_labels.classify_label("codex") == "bloat"
    assert cleanup_labels.classify_label("team:triage") == "idiosyncratic"


def test_classify_label_normalizes_case_and_colon_spacing() -> None:
    assert cleanup_labels.classify_label(" Agent:Codex ") == "functional"
    assert cleanup_labels.classify_label("Priority : High") == "informational"
    assert cleanup_labels.classify_label("Priority, High") == "informational"
    assert cleanup_labels.classify_label("SIZE:xs") == "bloat"


def test_classify_label_names_preserves_original_label_names() -> None:
    labels = [" Agent:Codex ", "Priority : High", "SIZE:xs", "team:triage"]

    result = cleanup_labels.classify_label_names(labels)

    assert result == {
        "functional": [" Agent:Codex "],
        "informational": ["Priority : High"],
        "bloat": ["SIZE:xs"],
        "idiosyncratic": ["team:triage"],
    }


def test_get_repo_labels_converts_github_labels() -> None:
    repo = FakeRepo([FakeLabel("bug", color="d73a4a", description=None)])

    labels = cleanup_labels.get_repo_labels(FakeGithub(repo), "owner/repo")

    assert labels == [cleanup_labels.LabelInfo(name="bug", color="d73a4a", description="")]


def test_audit_repo_classifies_fake_repo_without_mutation(capsys) -> None:
    bloat = FakeLabel("codex")
    repo = FakeRepo(
        [
            FakeLabel("agent:codex"),
            FakeLabel("Priority : High"),
            bloat,
            FakeLabel("team:triage"),
        ]
    )

    result = cleanup_labels.audit_repo(FakeGithub(repo), "owner/repo")

    assert result["total_labels"] == 4
    assert result["functional"] == ["agent:codex"]
    assert result["informational"] == ["Priority : High"]
    assert result["bloat"] == ["codex"]
    assert result["idiosyncratic"] == ["team:triage"]
    assert bloat.deleted is False
    assert "BLOAT LABELS TO REMOVE" in capsys.readouterr().out


def test_remove_labels_requires_confirm_before_delete() -> None:
    label = FakeLabel("codex")
    repo = FakeRepo([label])

    result = cleanup_labels.remove_labels(FakeGithub(repo), "owner/repo", ["codex"], confirm=False)

    assert result == {"removed": [], "errors": []}
    assert label.deleted is False


def test_remove_labels_deletes_only_requested_labels_when_confirmed() -> None:
    bloat = FakeLabel("codex")
    keep = FakeLabel("agent:codex")
    repo = FakeRepo([bloat, keep])

    result = cleanup_labels.remove_labels(FakeGithub(repo), "owner/repo", ["codex"], confirm=True)

    assert result == {"removed": ["codex"], "errors": []}
    assert bloat.deleted is True
    assert keep.deleted is False


def test_get_github_client_reports_missing_pygithub(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cleanup_labels, "Github", None)

    try:
        cleanup_labels.get_github_client()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit")

    assert "PyGithub not installed" in capsys.readouterr().out


def test_get_github_client_reports_missing_token(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cleanup_labels, "Github", SimpleNamespace)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    try:
        cleanup_labels.get_github_client()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit")

    assert "GITHUB_TOKEN environment variable not set" in capsys.readouterr().out
