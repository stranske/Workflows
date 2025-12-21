"""Service A module used for monorepo CI simulation."""

def ping(value: str) -> str:
    """Echo back a namespaced payload to validate packaging and tests."""

    return f"service-a:{value}"
