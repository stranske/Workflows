from pathlib import Path

from scripts.check_template_drift import WORKFLOW_ALIAS_MAPPINGS, discover_workflow_pairs

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pair_discovery_covers_every_shared_basename() -> None:
    main_dir = REPO_ROOT / ".github" / "workflows"
    template_dir = REPO_ROOT / "templates" / "consumer-repo" / ".github" / "workflows"
    main_names = {p.name for p in main_dir.glob("*.yml")}
    template_names = {p.name for p in template_dir.glob("*.yml")}
    shared = {
        name for name in main_names & template_names
        if WORKFLOW_ALIAS_MAPPINGS.get(name, name) in template_names
    }
    covered = {pair.main_path.name for pair in discover_workflow_pairs(REPO_ROOT)}
    missing = sorted(shared - covered)
    assert not missing, (
        "these basenames exist in BOTH .github/workflows/ and "
        "templates/consumer-repo/.github/workflows/ but have no drift pair: " + ", ".join(missing)
    )
