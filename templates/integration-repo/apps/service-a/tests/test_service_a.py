from service_a import ping


def test_ping_returns_namespaced_value() -> None:
    assert ping("ok") == "service-a:ok"
