from scripts.autofix_safe_sweep import dir_to_glob, matches_any


def test_root_glob_avoids_dot_prefix() -> None:
    assert dir_to_glob(".") == "**"
    assert dir_to_glob("./") == "**"
    assert matches_any("main.py", [dir_to_glob(".")])
    assert not matches_any("main.py", ["./**"])
