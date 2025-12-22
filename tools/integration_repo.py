from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_WORKFLOW_REF = "stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main"
WORKFLOW_PLACEHOLDER = "__WORKFLOW_REF__"
TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "templates" / "integration-repo"


def render_integration_repo(destination: Path, workflow_ref: str | None = None) -> Path:
    """
    Materialize the integration test consumer repository template.

    The template ships inside this repository under ``templates/integration-repo`` and includes
    a minimal Python project plus CI wiring that exercises the reusable workflows. Placeholder
    values inside the template are rewritten to point at the requested ``workflow_ref``.

    Args:
        destination: Target directory where the template should be rendered.
        workflow_ref: Reusable workflow reference (``owner/repo/.github/workflows/file@ref``).

    Returns:
        The destination path after rendering.

    Raises:
        FileExistsError: When the destination directory already contains files.
        FileNotFoundError: When the template root cannot be located.
    """

    if not TEMPLATE_ROOT.exists():
        raise FileNotFoundError(f"Template directory missing: {TEMPLATE_ROOT}")

    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Destination {destination} is not empty; refusing to overwrite.")

    destination.mkdir(parents=True, exist_ok=True)

    resolved_ref = workflow_ref or DEFAULT_WORKFLOW_REF

    for item in TEMPLATE_ROOT.rglob("*"):
        relative = item.relative_to(TEMPLATE_ROOT)
        target = destination / relative

        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            content = item.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            target.write_bytes(item.read_bytes())
            continue

        rewritten = content.replace(WORKFLOW_PLACEHOLDER, resolved_ref)
        target.write_text(rewritten, encoding="utf-8")

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the integration test consumer template")
    parser.add_argument("destination", type=Path, help="Path where the template should be copied")
    parser.add_argument(
        "--workflow-ref",
        default=DEFAULT_WORKFLOW_REF,
        help="Reusable workflow reference to embed in the consumer workflow",
    )

    args = parser.parse_args()
    render_integration_repo(args.destination, workflow_ref=args.workflow_ref)


if __name__ == "__main__":
    main()
