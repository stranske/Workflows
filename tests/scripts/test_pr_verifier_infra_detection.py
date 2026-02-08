"""Tests for infrastructure change-type classification in pr_verifier."""

from __future__ import annotations

import textwrap

from scripts.langchain.pr_verifier import (
    INFRA_THRESHOLD,
    _classify_change_type,
    _prepare_prompt,
)

# ---------------------------------------------------------------------------
# _classify_change_type
# ---------------------------------------------------------------------------


class TestClassifyChangeType:
    """Unit tests for _classify_change_type()."""

    def test_none_diff_returns_application(self):
        assert _classify_change_type(None) == "application"

    def test_empty_diff_returns_application(self):
        assert _classify_change_type("") == "application"
        assert _classify_change_type("   ") == "application"

    def test_pure_infrastructure_diff(self):
        diff = textwrap.dedent("""\
            diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
            --- a/.github/workflows/ci.yml
            +++ b/.github/workflows/ci.yml
            @@ -1,3 +1,4 @@
             name: CI
            +  timeout-minutes: 30
             on: push
            diff --git a/scripts/deploy.sh b/scripts/deploy.sh
            --- a/scripts/deploy.sh
            +++ b/scripts/deploy.sh
            @@ -1 +1 @@
            -echo "old"
            +echo "new"
        """)
        assert _classify_change_type(diff) == "infrastructure"

    def test_pure_application_diff(self):
        diff = textwrap.dedent("""\
            diff --git a/src/main.py b/src/main.py
            --- a/src/main.py
            +++ b/src/main.py
            @@ -1 +1 @@
            -print("hello")
            +print("world")
            diff --git a/tests/test_main.py b/tests/test_main.py
            --- a/tests/test_main.py
            +++ b/tests/test_main.py
            @@ -1 +1 @@
            -assert True
            +assert 1 == 1
        """)
        assert _classify_change_type(diff) == "application"

    def test_mixed_diff(self):
        # 2 infra + 2 app files → 50% → below threshold → mixed or application
        diff = textwrap.dedent("""\
            diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
            --- a/.github/workflows/ci.yml
            +++ b/.github/workflows/ci.yml
            @@ -1 +1 @@
            -old
            +new
            diff --git a/scripts/run.sh b/scripts/run.sh
            --- a/scripts/run.sh
            +++ b/scripts/run.sh
            @@ -1 +1 @@
            -old
            +new
            diff --git a/src/app.py b/src/app.py
            --- a/src/app.py
            +++ b/src/app.py
            @@ -1 +1 @@
            -old
            +new
            diff --git a/tests/test_app.py b/tests/test_app.py
            --- a/tests/test_app.py
            +++ b/tests/test_app.py
            @@ -1 +1 @@
            -old
            +new
        """)
        result = _classify_change_type(diff)
        assert result in ("mixed", "application")

    def test_docs_only_is_infrastructure(self):
        diff = textwrap.dedent("""\
            diff --git a/docs/guide.md b/docs/guide.md
            --- a/docs/guide.md
            +++ b/docs/guide.md
            @@ -1 +1 @@
            -old
            +new
            diff --git a/README.md b/README.md
            --- a/README.md
            +++ b/README.md
            @@ -1 +1 @@
            -old
            +new
        """)
        assert _classify_change_type(diff) == "infrastructure"

    def test_templates_are_infrastructure(self):
        diff = textwrap.dedent("""\
            diff --git a/templates/consumer-repo/.github/workflows/ci.yml b/templates/consumer-repo/.github/workflows/ci.yml
            --- a/templates/consumer-repo/.github/workflows/ci.yml
            +++ b/templates/consumer-repo/.github/workflows/ci.yml
            @@ -1 +1 @@
            -old
            +new
        """)
        assert _classify_change_type(diff) == "infrastructure"

    def test_config_files_are_infrastructure(self):
        diff = textwrap.dedent("""\
            diff --git a/pyproject.toml b/pyproject.toml
            --- a/pyproject.toml
            +++ b/pyproject.toml
            @@ -1 +1 @@
            -old
            +new
            diff --git a/Makefile b/Makefile
            --- a/Makefile
            +++ b/Makefile
            @@ -1 +1 @@
            -old
            +new
        """)
        assert _classify_change_type(diff) == "infrastructure"

    def test_no_diff_headers_returns_application(self):
        # Random text that doesn't contain diff headers
        assert _classify_change_type("just some random text\nwithout diff headers") == "application"

    def test_threshold_boundary(self):
        """Ensure threshold is respected: 3 infra + 2 app = 60% → infrastructure."""
        diff = "\n".join(
            [
                "diff --git a/.github/workflows/a.yml b/.github/workflows/a.yml",
                "diff --git a/scripts/b.sh b/scripts/b.sh",
                "diff --git a/docs/c.md b/docs/c.md",
                "diff --git a/src/d.py b/src/d.py",
                "diff --git a/lib/e.py b/lib/e.py",
            ]
        )
        assert INFRA_THRESHOLD == 0.6
        assert _classify_change_type(diff) == "infrastructure"


# ---------------------------------------------------------------------------
# _prepare_prompt integration with infra detection
# ---------------------------------------------------------------------------


class TestPreparePromptInfraSelection:
    """Verify _prepare_prompt selects the correct prompt variant."""

    def _infra_diff(self) -> str:
        return textwrap.dedent("""\
            diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
            --- a/.github/workflows/ci.yml
            +++ b/.github/workflows/ci.yml
            @@ -1 +1 @@
            -old
            +new
        """)

    def _app_diff(self) -> str:
        return textwrap.dedent("""\
            diff --git a/src/main.py b/src/main.py
            --- a/src/main.py
            +++ b/src/main.py
            @@ -1 +1 @@
            -old
            +new
        """)

    def test_app_diff_uses_standard_prompt(self):
        result = _prepare_prompt("context", self._app_diff())
        # Standard prompt does NOT contain "infrastructure" emphasis
        assert "infrastructure and platform files" not in result
        assert "context" in result

    def test_infra_diff_uses_relaxed_prompt(self):
        result = _prepare_prompt("context", self._infra_diff())
        # Infra addendum should be appended (whether custom prompt or default)
        assert "Infrastructure Change Guidance" in result
        assert "LENIENT on test coverage" in result

    def test_infra_prompt_still_has_required_fields(self):
        result = _prepare_prompt("context", self._infra_diff())
        for field in ("correctness", "completeness", "quality", "testing", "risks"):
            assert field in result

    def test_no_diff_uses_standard_prompt(self):
        result = _prepare_prompt("context", None)
        assert "Infrastructure Change Guidance" not in result
