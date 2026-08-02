from datetime import UTC, datetime

import pytest
from scripts.dev_tool_update_policy import should_propose_update


def test_routine_updates_are_limited_to_the_weekly_utc_window():
    monday = datetime(2026, 8, 3, 3, 0, tzinfo=UTC)
    tuesday = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)

    assert should_propose_update(monday, security_override=False)
    assert not should_propose_update(tuesday, security_override=False)


def test_security_override_bypasses_the_routine_window():
    tuesday = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)

    assert should_propose_update(tuesday, security_override=True)


def test_policy_requires_an_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        should_propose_update(datetime(2026, 8, 3, 3, 0), security_override=False)
