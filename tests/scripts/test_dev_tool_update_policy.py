from datetime import UTC, datetime

import pytest
from scripts.dev_tool_update_policy import main, should_propose_update


def test_routine_updates_are_limited_to_the_weekly_utc_window():
    monday = datetime(2026, 8, 3, 3, 0, tzinfo=UTC)
    tuesday = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)

    assert should_propose_update(monday, security_override=False)
    assert not should_propose_update(tuesday, security_override=False)


def test_policy_uses_the_utc_weekday_at_a_timezone_boundary():
    # Local Sunday evening in US/Eastern is already Monday UTC.
    now = datetime.fromisoformat("2026-08-02T20:30:00-04:00")

    assert should_propose_update(now, security_override=False) is True


def test_security_override_bypasses_the_routine_window():
    tuesday = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)

    assert should_propose_update(tuesday, security_override=True)


def test_policy_requires_an_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        should_propose_update(datetime(2026, 8, 3, 3, 0), security_override=False)


def test_cli_reports_the_weekly_window_output_contract(capsys):
    assert main(["--at", "2026-08-03T03:00:00Z"]) == 0

    assert capsys.readouterr().out == "should_propose=true\nreason=weekly_window\n"


def test_cli_reports_a_skipped_routine_window(capsys):
    assert main(["--at", "2026-08-04T03:00:00Z"]) == 0

    assert capsys.readouterr().out == "should_propose=false\nreason=outside_weekly_window\n"


def test_cli_reports_the_security_override_output_contract(capsys):
    assert main(["--at", "2026-08-04T03:00:00Z", "--security-override"]) == 0

    assert capsys.readouterr().out == "should_propose=true\nreason=security_override\n"
