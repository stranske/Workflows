"""Regression test for ARG002 unused method argument violations.

This test ensures that the fixes for issue #4484 (unused config arguments in
_llm_client.py:40 and pr_verifier.py:8735) remain in place and that no new
ARG002 violations are introduced.

The test runs ruff with ARG002 enabled against the authoritative source files
and verifies that no violations are found.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# The authoritative source files that sync to consumer repos
SOURCE_FILES = [
    Path("scripts/langchain/_llm_client.py"),
    Path("scripts/langchain/pr_verifier.py"),
]


def test_no_arg002_violations() -> None:
    """Verify that no ARG002 violations exist in the source files."""
    # Run ruff check with ARG002 enabled
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "ARG002"] + [str(f) for f in SOURCE_FILES],
        capture_output=True,
        text=True,
    )

    # Should exit successfully with no output
    assert result.returncode == 0, (
        f"ruff check --select ARG002 failed with exit code {result.returncode}:\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert result.stdout.strip() == "" or "All checks passed" in result.stdout, (
        f"Unexpected ruff output: {result.stdout}"
    )


def test_config_parameter_present_in_invoke() -> None:
    """Verify that the config parameter is still present in invoke method signatures.
    
    This ensures we haven't accidentally removed the parameter, which would
    break the calling contract.
    """
    # Check _llm_client.py
    llm_client_path = Path("scripts/langchain/_llm_client.py")
    llm_client_content = llm_client_path.read_text()
    
    # The SubscriptionClientAdapter.invoke should have config parameter
    assert "def invoke(self, prompt: Any, config: Any = None" in llm_client_content, (
        "SubscriptionClientAdapter.invoke should have config parameter"
    )
    
    # And it should pass config to the underlying client
    assert "return self.client.invoke(prompt, config=config, **kwargs)" in llm_client_content, (
        "SubscriptionClientAdapter.invoke should pass config to underlying client"
    )
    
    # Check pr_verifier.py
    pr_verifier_path = Path("scripts/langchain/pr_verifier.py")
    pr_verifier_content = pr_verifier_path.read_text()
    
    # The CapacityBackupClient.invoke should have config parameter
    assert "def invoke(self, prompt: str, config: Any = None" in pr_verifier_content, (
        "CapacityBackupClient.invoke should have config parameter"
    )
    
    # And it should have the noqa comment for ARG002
    assert "# noqa: ARG002" in pr_verifier_content, (
        "CapacityBackupClient.invoke should have noqa: ARG002 comment"
    )


if __name__ == "__main__":
    test_no_arg002_violations()
    test_config_parameter_present_in_invoke()
    print("All ARG002 regression tests passed!")
