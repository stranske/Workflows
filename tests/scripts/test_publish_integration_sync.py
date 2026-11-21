"""Exercise the Maint 69 publication against a real local Git receiver."""

from pathlib import Path

import pytest
from scripts import publish_integration_sync as delivery

MANAGED = Path(".github/scripts/managed.js")
UNRELATED = Path("docs/LABELS.md")


def git(repo: Path, *args: str) -> str:
    return delivery.git(repo, *args).stdout.decode().strip()


def install(repo: Path, path: Path, contents: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents)


def commit(repo: Path, title: str) -> None:
    git(repo, "add", ".")
    git(repo, "commit", "-m", title)


def clone(root: Path, remote: Path, name: str) -> Path:
    repo = root / name
    git(root, "clone", "--depth=1", remote.as_uri(), str(repo))
    git(repo, "config", "user.name", "Integration fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    return repo


def seed_receiver(root: Path) -> tuple[Path, Path, Path, Path]:
    remote = root / "remote.git"
    git(root, "init", "--bare", "--initial-branch=main", str(remote))
    seed = clone(root, remote, "seed")
    for path in delivery.DELIVERY_PATHS:
        if "." in Path(path).name:
            install(seed, Path(path), "tracked before sync\n")
        else:
            install(seed, Path(path) / "placeholder", "tracked before sync\n")
    install(seed, MANAGED, "old content\n")
    install(seed, UNRELATED, "before racing edit\n")
    commit(seed, "Seed receiver")
    git(seed, "push", "origin", "main")

    receiver = clone(root, remote, "integration-tests")
    competitor = clone(root, remote, "competitor")
    script = root / "apply.sh"
    script.write_text(
        "set -eu\n"
        "printf '%s\\n' applied >> replay-count\n"
        "printf '%s\\n' 'canonical content' > integration-tests/.github/scripts/managed.js\n"
    )
    return remote, receiver, competitor, script


@pytest.mark.parametrize(
    "change",
    ["unrelated", "identical", "modify", "create", "delete", "rename", "executable", "symlink"],
)
def test_retry_preserves_concurrent_receiver_changes(tmp_path, monkeypatch, change):
    remote, receiver, competitor, apply_script = seed_receiver(tmp_path)
    target = competitor / MANAGED
    actual_push = delivery.push
    push_attempts = []
    if change == "create":
        (receiver / MANAGED).unlink()
        commit(receiver, "Remove path before the real fixture race")
        git(receiver, "push", "origin", "main")
        git(competitor, "pull", "--ff-only")

    def race_push(repo, ref):
        if not push_attempts:
            install(competitor, UNRELATED, "racing docs edit\n")
            if change in {"modify", "create", "identical"}:
                text = "canonical content\n" if change == "identical" else "local edit\n"
                install(competitor, MANAGED, text)
            elif change == "delete":
                target.unlink()
            elif change == "rename":
                target.rename(target.with_suffix(".old"))
            elif change == "executable":
                target.chmod(0o755)
            elif change == "symlink":
                target.unlink()
                target.symlink_to("../../docs/LABELS.md")
            commit(competitor, "Concurrent receiver commit")
            git(competitor, "push", "origin", "main")
        push_attempts.append(ref)
        return actual_push(repo, ref)

    monkeypatch.setattr(delivery, "push", race_push)
    install(receiver, MANAGED, "canonical content\n")
    if change in {"unrelated", "identical"}:
        assert delivery.publish(receiver, apply_script, ["Delivery"]) is (change == "unrelated")
        assert (tmp_path / "replay-count").read_text() == "applied\n"
        assert len(push_attempts) == (2 if change == "unrelated" else 1)
        assert git(remote, "show", f"main:{MANAGED}") == "canonical content"
        git(remote, "merge-base", "--is-ancestor", git(competitor, "rev-parse", "HEAD"), "main")
    else:
        with pytest.raises(delivery.PublicationError, match="Concurrent"):
            delivery.publish(receiver, apply_script, ["Delivery"])
        assert len(push_attempts) == 1
        assert not (tmp_path / "replay-count").exists()
        assert git(remote, "rev-parse", "main") == git(competitor, "rev-parse", "HEAD")
    assert git(remote, "show", f"main:{UNRELATED}") == "racing docs edit"


def test_remote_hook_failure_does_not_recompute(tmp_path):
    remote, receiver, _, apply_script = seed_receiver(tmp_path)
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'receiver policy denial' >&2\nexit 1\n")
    hook.chmod(0o755)
    install(receiver, MANAGED, "canonical content\n")
    with pytest.raises(delivery.PublicationError, match="without a default-branch race"):
        delivery.publish(receiver, apply_script, ["Delivery"])
    assert not (tmp_path / "replay-count").exists()
    assert git(remote, "show", f"main:{MANAGED}") == "old content"


def test_second_concurrent_push_stops_after_one_recompute(tmp_path, monkeypatch):
    remote, receiver, competitor, apply_script = seed_receiver(tmp_path)
    actual_push = delivery.push
    push_attempts = []

    def race_push(repo, ref):
        push_attempts.append(ref)
        install(competitor, UNRELATED, f"racing docs edit {len(push_attempts)}\n")
        commit(competitor, "Concurrent receiver commit")
        git(competitor, "push", "origin", "main")
        return actual_push(repo, ref)

    monkeypatch.setattr(delivery, "push", race_push)
    install(receiver, MANAGED, "canonical content\n")
    with pytest.raises(delivery.PublicationError, match="after one fresh recomputation"):
        delivery.publish(receiver, apply_script, ["Delivery"])
    assert len(push_attempts) == 2
    assert (tmp_path / "replay-count").read_text() == "applied\n"
    assert git(remote, "show", f"main:{MANAGED}") == "old content"
    assert git(remote, "show", f"main:{UNRELATED}") == "racing docs edit 2"


def test_initial_publication_stages_add_remove_and_optional_path(tmp_path):
    remote, receiver, _, apply_script = seed_receiver(tmp_path)
    (receiver / MANAGED).unlink()
    created = MANAGED.with_name("created.js")
    install(receiver, created, "canonical new payload\n")
    install(receiver, Path(delivery.OPTIONAL_DELIVERY_PATH), "published optional config\n")
    assert delivery.publish(receiver, apply_script, ["Delivery"])
    assert not (tmp_path / "replay-count").exists()
    assert git(remote, "show", f"main:{created}") == "canonical new payload"
    assert git(remote, "ls-tree", "main", "--", str(MANAGED)) == ""
    assert git(remote, "show", f"main:{delivery.OPTIONAL_DELIVERY_PATH}") == (
        "published optional config"
    )


def test_initial_publication_only_requires_the_configured_upstream(tmp_path):
    remote, receiver, _, apply_script = seed_receiver(tmp_path)
    git(receiver, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
    assert git(receiver, "rev-parse", "--symbolic-full-name", "@{upstream}") == (
        "refs/remotes/origin/main"
    )
    install(receiver, MANAGED, "canonical content\n")
    assert delivery.publish(receiver, apply_script, ["Delivery"])
    assert not (tmp_path / "replay-count").exists()
    assert git(remote, "show", f"main:{MANAGED}") == "canonical content"


def test_retry_refuses_to_restore_withdrawn_receiver_history(tmp_path, monkeypatch):
    remote, receiver, competitor, apply_script = seed_receiver(tmp_path)
    original = git(receiver, "rev-parse", "HEAD")
    actual_push = delivery.push
    push_attempts = []

    def race_push(repo, ref):
        push_attempts.append(ref)
        if len(push_attempts) == 1:
            install(competitor, UNRELATED, "concurrent change later withdrawn\n")
            commit(competitor, "Receiver advanced")
            git(competitor, "push", "origin", "main")
        else:
            git(remote, "update-ref", ref, original)
        return actual_push(repo, ref)

    monkeypatch.setattr(delivery, "push", race_push)
    install(receiver, MANAGED, "canonical content\n")
    with pytest.raises(delivery.PublicationError, match="after one fresh recomputation"):
        delivery.publish(receiver, apply_script, ["Delivery"])
    assert len(push_attempts) == 2
    assert git(remote, "rev-parse", "main") == original
    assert git(remote, "show", f"main:{MANAGED}") == "old content"
