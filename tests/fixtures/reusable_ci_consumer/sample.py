"""Small real consumer used to exercise reusable CI features and branch reports."""


def classify_size(value: int) -> str:
    """Classify a nonnegative count, rejecting invalid negative input."""
    if value < 0:
        raise ValueError("count must be nonnegative")
    if value == 0:
        return "empty"
    if value < 10:
        return "small"
    return "large"
