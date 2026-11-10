"""Keep the required follow-up test command usable with Python 3.14 plugins."""

import warnings

import pytest
from _pytest.config import parse_warning_filter

LANGSMITH_MODULE = "langsmith._internal._beta_decorator"
COROUTINE_DEPRECATION = (
    "'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; "
    "use inspect.iscoroutinefunction() instead"
)


@pytest.fixture
def repository_warning_policy(pytestconfig):
    with warnings.catch_warnings():
        warnings.resetwarnings()
        for entry in pytestconfig.getini("filterwarnings"):
            warnings.filterwarnings(*parse_warning_filter(entry, escape=False))
        yield


def test_langsmith_plugin_coroutine_deprecation_allows_startup(repository_warning_policy):
    warnings.warn_explicit(
        COROUTINE_DEPRECATION,
        DeprecationWarning,
        filename="langsmith/_internal/_beta_decorator.py",
        lineno=92,
        module=LANGSMITH_MODULE,
    )


@pytest.mark.parametrize(
    "message, category, module",
    [
        (COROUTINE_DEPRECATION, DeprecationWarning, "scripts.langchain.followup_issue_generator"),
        (COROUTINE_DEPRECATION, DeprecationWarning, LANGSMITH_MODULE + "_other"),
        ("Another deprecated API", DeprecationWarning, LANGSMITH_MODULE),
        (COROUTINE_DEPRECATION, RuntimeWarning, LANGSMITH_MODULE),
    ],
    ids=["production-module", "sibling-module", "different-deprecation", "different-category"],
)
def test_unrelated_warnings_remain_errors(repository_warning_policy, message, category, module):
    with pytest.raises(category, match="deprecated"):
        warnings.warn_explicit(
            message, category, filename="warning-source.py", lineno=1, module=module
        )
