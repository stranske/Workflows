"""Publish Maint 69's integration sync, with one retry on an advanced default."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DELIVERY_PATHS = (
    ".github/workflows",
    ".github/actions",
    ".github/scripts",
    "scripts",
    "pyproject.toml",
    "requirements.lock",
    "tools/coverage_guard.py",
)
OPTIONAL_DELIVERY_PATH = ".pre-commit-config.yaml"
RACE_REJECTIONS = {b"[rejected] (fetch first)", b"[rejected] (non-fast-forward)"}
MAX_FETCH_DEPTH = 8


class PublicationError(RuntimeError):
    """The integration publication must stop and leave the alert to its caller."""


def git(
    repo: Path, *args: str, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, check=check, capture_output=capture)


def revision(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").stdout.decode().strip()


def receiver_default(repo: Path, branch: str) -> str:
    lines = git(repo, "ls-remote", "--symref", "origin", "HEAD").stdout.decode().splitlines()
    symbolic = f"ref: {branch}\tHEAD"
    if symbolic not in lines:
        raise PublicationError("The receiver no longer advertises the cloned default branch")
    return next((line.removesuffix("\tHEAD") for line in lines if line != symbolic), "")


def changed_paths(repo: Path, before: str, after: str) -> set[bytes]:
    output = git(repo, "diff", "--no-renames", "--name-only", "-z", before, after, "--").stdout
    return set(output.split(b"\0")) - {b""}


def tree_entry(repo: Path, ref: str, path: bytes) -> bytes:
    return git(repo, "--literal-pathspecs", "ls-tree", "-z", ref, "--", os.fsdecode(path)).stdout


def paths_overlap(left: bytes, right: bytes) -> bool:
    return left == right or left.startswith(right + b"/") or right.startswith(left + b"/")


def race_rejection(result: subprocess.CompletedProcess[bytes], ref: str) -> bool:
    rows = [line.split(b"\t") for line in result.stdout.splitlines() if line[1:2] == b"\t"]
    if len(rows) != 1 or len(rows[0]) != 3:
        return False
    flag, ref_spec, reason = rows[0]
    return flag == b"!" and ref_spec.endswith(b":" + ref.encode()) and reason in RACE_REJECTIONS


def push(repo: Path, ref: str) -> subprocess.CompletedProcess[bytes]:
    result = git(repo, "push", "--porcelain", "origin", f"HEAD:{ref}", check=False)
    print(result.stdout.decode(errors="replace"), end="", flush=True)
    print(result.stderr.decode(errors="replace"), end="", file=sys.stderr, flush=True)
    return result


def stage_delivery(repo: Path) -> None:
    git(repo, "add", "--", *DELIVERY_PATHS)
    if (repo / OPTIONAL_DELIVERY_PATH).is_file():
        git(repo, "add", "--", OPTIONAL_DELIVERY_PATH)


def commit_delivery(repo: Path, messages: list[str]) -> None:
    args = [argument for message in messages for argument in ("-m", message)]
    git(repo, "commit", *args, capture=False)


def publish(repo: Path, apply_script: Path, messages: list[str]) -> bool:
    branch = git(repo, "symbolic-ref", "HEAD").stdout.decode().strip()
    upstream = git(repo, "rev-parse", "--symbolic-full-name", "@{upstream}").stdout.decode().strip()
    if upstream != "refs/remotes/origin/" + branch.removeprefix("refs/heads/"):
        raise PublicationError("The receiver checkout does not track its cloned branch on origin")

    base = revision(repo, "HEAD")
    stage_delivery(repo)
    commit_delivery(repo, messages)
    pending = revision(repo, "HEAD")
    first = push(repo, branch)
    if first.returncode == 0:
        return True
    if not race_rejection(first, branch):
        raise PublicationError("Integration push failed without a default-branch race")

    advertised = receiver_default(repo, branch)
    git(repo, "fetch", "--no-tags", f"--deepen={MAX_FETCH_DEPTH}", "origin", branch)
    advanced = revision(repo, "FETCH_HEAD")
    ancestor = git(repo, "merge-base", "--is-ancestor", base, advanced, check=False)
    if advanced != advertised or advanced == base or ancestor.returncode != 0:
        raise PublicationError("Cannot verify that the receiver default advanced from the checkout")

    incoming = changed_paths(repo, base, advanced)
    outgoing = changed_paths(repo, base, pending)
    writable = tuple(path.encode() for path in (*DELIVERY_PATHS, OPTIONAL_DELIVERY_PATH))
    for path in sorted(incoming):
        if not any(paths_overlap(path, target) for target in writable):
            continue
        entry = tree_entry(repo, advanced, path)
        if entry.startswith(b"120000 "):
            raise PublicationError(f"Concurrent symlink in the integration delivery: {path!r}")
        for proposed in outgoing:
            if paths_overlap(path, proposed) and (
                path != proposed or entry != tree_entry(repo, pending, path)
            ):
                raise PublicationError(f"Concurrent managed change preserved: {path!r}")

    # Push from a depth-one boundary at the verified parent. An ordinary push
    # must reject a later rewind instead of treating it as an ancestor to restore.
    git(repo, "fetch", "--no-tags", "--depth=1", "origin", branch)
    if revision(repo, "FETCH_HEAD") != advanced:
        raise PublicationError("Receiver default moved again before recomputation")

    print("Receiver default advanced; recomputing the delivery once", flush=True)
    git(repo, "checkout", "--detach", advanced, capture=False)
    subprocess.run(["bash", str(apply_script)], cwd=repo.parent, check=True)
    stage_delivery(repo)
    staged = git(repo, "diff", "--cached", "--no-renames", "--name-only", "-z", "--").stdout
    recomputed = set(staged.split(b"\0")) - {b""}
    if any(paths_overlap(path, proposed) for path in incoming for proposed in recomputed):
        raise PublicationError("Recomputed delivery would change a concurrent receiver path")
    if recomputed:
        commit_delivery(repo, messages)

    # Recheck the default setting after rendering and before publication.
    # The subsequent native push separately guards the target ref update.
    if receiver_default(repo, branch) != advanced:
        raise PublicationError("The receiver default moved again during recomputation")
    if not recomputed:
        print("No changes needed after recomputing from the current receiver default")
        return False
    if push(repo, branch).returncode != 0:
        raise PublicationError("Integration push failed after one fresh recomputation")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--apply-script", type=Path, required=True)
    parser.add_argument("-m", dest="messages", action="append", required=True)
    args = parser.parse_args()
    try:
        pushed = publish(args.repo.resolve(), args.apply_script.resolve(), args.messages)
    except (PublicationError, subprocess.CalledProcessError, OSError) as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    outcome = f"published={'true' if pushed else 'false'}"
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(outcome + "\n")
    print(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
