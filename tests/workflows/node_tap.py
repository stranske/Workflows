"""Assertions for workflow contracts that run one named Node regression."""

import re
from subprocess import CompletedProcess

import pytest


def assert_named_node_test(result: CompletedProcess[str], name: str) -> None:
    """Reject the passing file-level TAP record Node emits for an unmatched selector."""
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    passed = re.compile(rf"ok [0-9]+ - {re.escape(name)}")
    if (
        lines.count(f"# Subtest: {name}") != 1
        or sum(passed.fullmatch(line) is not None for line in lines) != 1
    ):
        pytest.fail(
            f"Expected exactly one passing Node testcase named {name!r}:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
