"""Exercise real manifest rendering across immutable commits, without GitHub."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "consumer_delivery_digest", ROOT / "scripts/consumer_delivery_digest.py"
)
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@pytest.fixture
def source(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / ".github").mkdir()
    (tmp_path / "templates/consumer-repo").mkdir(parents=True)
    (tmp_path / "templates/consumer-repo/.gitignore").write_bytes(
        (ROOT / "templates/consumer-repo/.gitignore").read_bytes()
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/copied.js").write_text("console.log('delivered');\n")
    (tmp_path / ".github/sync-manifest.yml").write_text("""version: 1
scripts:
  - source: scripts/copied.js
    target: scripts/rendered.js
    description: test delivery
removals:
  - target: obsolete.js
    description: obsolete
""")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def commit(root):
    git(root, "add", ".")
    git(root, "commit", "-qm", "change")
    return git(root, "rev-parse", "HEAD")


def test_unchanged_generated_payload_across_shas(source):
    first = digest.payload_at_ref(source, git(source, "rev-parse", "HEAD"), ["owner/repo"])
    (source / "README.md").write_text("unrelated main activity\n")
    second = digest.payload_at_ref(source, commit(source), ["owner/repo"])
    assert first == second
    assert first["files"]["owner/repo"]["scripts/rendered.js"]["content"]
    assert first["files"]["owner/repo"]["obsolete.js"] == {"remove": True}


def test_delivered_bytes_change_digest(source):
    before = digest.render_payload(source, ["owner/repo"])
    (source / "scripts/copied.js").write_text("console.log('new payload');\n")
    assert digest.render_payload(source, ["owner/repo"])["digest"] != before["digest"]


def test_descriptive_manifest_metadata_does_not_change_payload(source):
    before = digest.render_payload(source, ["owner/repo"])
    manifest = source / ".github/sync-manifest.yml"
    manifest.write_text(manifest.read_text().replace("test delivery", "better description"))
    assert digest.render_payload(source, ["owner/repo"]) == before


def test_scopes_create_only_directory_and_removal_change_identity(source):
    manifest = source / ".github/sync-manifest.yml"
    manifest.write_text(
        manifest.read_text().replace(
            "    description: test delivery",
            """    description: test delivery
    sync_mode: create_only
    overwrite_repos: [owner/overwrite]
    skip_repos:
      - repo: owner/excluded
        reason: local policy""",
        )
    )
    (source / "scripts/directory").mkdir()
    (source / "scripts/directory/child.js").write_text("child\n")
    manifest.write_text(
        manifest.read_text().replace(
            "removals:",
            """  - source: scripts/directory
    target: delivered-directory
    is_directory: true
    description: directory
removals:""",
        )
    )
    rendered = digest.render_payload(source, ["owner/repo", "owner/overwrite", "owner/excluded"])
    assert rendered["files"]["owner/repo"]["scripts/rendered.js"]["create_only"] is True
    assert rendered["files"]["owner/overwrite"]["scripts/rendered.js"]["create_only"] is False
    assert "scripts/rendered.js" not in rendered["files"]["owner/excluded"]
    assert "delivered-directory/child.js" in rendered["files"]["owner/repo"]
    (source / "scripts/directory/child.js").write_text("changed child\n")
    assert digest.render_payload(source, list(rendered["files"]))["digest"] != rendered["digest"]


def test_generated_status_block_participates_in_digest(source):
    before = digest.render_payload(source, ["owner/repo"])
    template = source / "templates/consumer-repo/.gitignore"
    template.write_text(
        template.read_text().replace(
            "# END WORKFLOWS STATUS FILES", "new-output.json\n# END WORKFLOWS STATUS FILES"
        )
    )
    after = digest.render_payload(source, ["owner/repo"])
    assert after["digest"] != before["digest"]
    assert after["files"]["owner/repo"][".gitignore"] != before["files"]["owner/repo"][".gitignore"]


def test_digest_is_order_independent_and_rejects_mutable_refs(source):
    assert digest.render_payload(source, ["owner/a", "owner/b"]) == digest.render_payload(
        source, ["owner/b", "owner/a"]
    )
    with pytest.raises(ValueError, match="immutable"):
        digest.payload_at_ref(source, "main", ["owner/repo"])
    assert json.dumps(digest.render_payload(source, ["owner/a"]))


def test_executable_mode_is_part_of_rendered_payload(source):
    first = digest.payload_at_ref(source, git(source, "rev-parse", "HEAD"), ["owner/repo"])
    (source / "scripts/copied.js").chmod(0o755)
    second = digest.payload_at_ref(source, commit(source), ["owner/repo"])
    assert second["digest"] != first["digest"]
    assert second["files"]["owner/repo"]["scripts/rendered.js"]["executable"] is True
