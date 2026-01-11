"""Basic autopilot sanity checks."""


def test_autopilot_hello():
    """Verify the autopilot test harness works."""
    assert "autopilot" in "hello autopilot"


def test_autopilot_message_prefix():
    """Confirm the sample message keeps the expected prefix."""
    message = "hello autopilot"
    assert message.startswith("hello")
