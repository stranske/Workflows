from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts import validate_version_pins


@pytest.mark.parametrize(
    ("spec", "version", "expected"),
    [
        (">=7.10.6", (7, 10, 6), True),
        (">7.10.6", (7, 10, 6), False),
        ("<=1.2", (1, 2, 0), True),
        ("<2", (2, 0), False),
        ("==3.4", (3, 4), True),
        ("!=3.4", (3, 4), False),
    ],
)
def test_version_constraint_parse_and_satisfied(
    spec: str, version: tuple[int, ...], expected: bool
) -> None:
    constraint = validate_version_pins.VersionConstraint.parse(spec)

    assert constraint is not None
    assert constraint.satisfied_by(version) is expected


def test_version_constraint_parse_rejects_invalid() -> None:
    assert validate_version_pins.VersionConstraint.parse("not-a-version") is None


def test_version_constraint_unknown_operator_returns_false() -> None:
    constraint = validate_version_pins.VersionConstraint("~=", (1, 0))

    assert constraint.satisfied_by((1, 0)) is False


def test_parse_version_handles_prerelease() -> None:
    assert validate_version_pins.parse_version("7.13.0rc1") == (7, 13, 0)
    assert validate_version_pins.parse_version("nope") == (0,)


def test_parse_env_file_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.env"

    assert validate_version_pins.parse_env_file(missing) == {}


def test_parse_env_file_reads_versions(tmp_path: Path) -> None:
    env_path = tmp_path / "pins.env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "PYTEST_VERSION=7.2.1",
                "MY_TOOL_VERSION=1.2.3",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    parsed = validate_version_pins.parse_env_file(env_path)

    assert parsed["pytest"] == "7.2.1"
    assert parsed["my-tool"] == "1.2.3"


@pytest.mark.parametrize(
    ("req", "expected"),
    [
        ("coverage[toml]>=7.10.6", ("coverage", [">=7.10.6"])),
        ("pytest>=7.0,<9", ("pytest", [">=7.0", "<9"])),
        ("requests", ("requests", [])),
        ("invalid$$$", ("invalid", ["$$$"])),
        ("; python_version < '3.8'", None),
        ("importlib-metadata; python_version < '3.8'", ("importlib-metadata", [])),
    ],
)
def test_extract_base_requirement(req: str, expected: tuple[str, list[str]] | None) -> None:
    assert validate_version_pins.extract_base_requirement(req) == expected


def test_check_compatibility_reports_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = {"pytest": "7.0.0", "pluggy": "1.0.0"}

    def fake_requires(package: str, version: str) -> list[str]:
        if package == "pytest":
            return ["pluggy>=2.0"]
        return []

    monkeypatch.setattr(validate_version_pins, "get_package_requires", fake_requires)

    errors = validate_version_pins.check_compatibility(versions)

    assert len(errors) == 1
    assert "INCOMPATIBLE" in errors[0]


def test_check_compatibility_ignores_unpinned_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = {"pytest": "7.0.0"}

    monkeypatch.setattr(
        validate_version_pins,
        "get_package_requires",
        lambda package, version: ["pluggy>=1.0"],
    )

    assert validate_version_pins.check_compatibility(versions) == []


def test_check_compatibility_skips_unparseable_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = {"pytest": "7.0.0"}

    monkeypatch.setattr(
        validate_version_pins,
        "get_package_requires",
        lambda package, version: ["; python_version < '3.8'"],
    )

    assert validate_version_pins.check_compatibility(versions) == []


def test_check_compatibility_skips_unparseable_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = {"pytest": "7.0.0", "pluggy": "1.0.0"}

    monkeypatch.setattr(
        validate_version_pins,
        "get_package_requires",
        lambda package, version: ["pluggy~=1.0"],
    )

    assert validate_version_pins.check_compatibility(versions) == []


def test_get_package_requires_returns_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"info": {"requires_dist": ["pluggy>=1.0"]}}).encode()

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return payload

    monkeypatch.setattr(
        validate_version_pins.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse()
    )

    assert validate_version_pins.get_package_requires("pytest", "7.0.0") == [
        "pluggy>=1.0"
    ]


def test_get_package_requires_handles_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        validate_version_pins.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert validate_version_pins.get_package_requires("pytest", "7.0.0") == []
    assert "Could not fetch pytest==7.0.0" in capsys.readouterr().out


def test_validate_file_no_versions(tmp_path: Path) -> None:
    env_path = tmp_path / "empty.env"
    env_path.write_text("", encoding="utf-8")

    errors, warnings = validate_version_pins.validate_file(env_path)

    assert errors == []
    assert warnings == ["No versions found in file"]


def test_validate_file_returns_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / "pins.env"
    env_path.write_text("PYTEST_VERSION=7.0.0\n", encoding="utf-8")

    monkeypatch.setattr(
        validate_version_pins, "check_compatibility", lambda versions: ["bad pin"]
    )

    errors, warnings = validate_version_pins.validate_file(env_path)

    assert errors == ["bad pin"]
    assert warnings == []


def test_main_single_file_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / "pins.env"
    env_path.write_text("PYTEST_VERSION=7.0.0\n", encoding="utf-8")

    monkeypatch.setattr(validate_version_pins, "get_package_requires", lambda *args: [])
    monkeypatch.setattr(
        validate_version_pins.sys, "argv", ["validate_version_pins.py", str(env_path)]
    )

    assert validate_version_pins.main() == 0


def test_main_single_file_reports_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / "pins.env"
    env_path.write_text("PYTEST_VERSION=7.0.0\n", encoding="utf-8")

    monkeypatch.setattr(
        validate_version_pins, "validate_file", lambda path: (["bad pin"], ["warn"])
    )
    monkeypatch.setattr(
        validate_version_pins.sys, "argv", ["validate_version_pins.py", str(env_path)]
    )

    assert validate_version_pins.main() == 1
    output = capsys.readouterr().out
    assert "bad pin" in output
    assert "warn" in output


def test_main_check_all_templates_reports_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = Path(validate_version_pins.__file__).parent.parent

    with TemporaryDirectory(dir=repo_root) as temp_dir:
        env_path = Path(temp_dir) / "autofix-versions.env"
        env_path.write_text("PYTEST_VERSION=7.0.0\n", encoding="utf-8")

        original_glob = Path.glob
        original_exists = Path.exists

        def fake_glob(self: Path, pattern: str) -> list[Path]:
            if self == repo_root and pattern == "templates/**/autofix-versions.env":
                return [env_path]
            return []

        def fake_exists(self: Path) -> bool:
            if str(self).endswith(".github/workflows/autofix-versions.env"):
                return False
            return original_exists(self)

        monkeypatch.setattr(Path, "glob", fake_glob)
        monkeypatch.setattr(Path, "exists", fake_exists)
        monkeypatch.setattr(
            validate_version_pins,
            "validate_file",
            lambda path: (["bad pin"], ["warn"]),
        )
        monkeypatch.setattr(
            validate_version_pins.sys,
            "argv",
            ["validate_version_pins.py", "--check-all-templates"],
        )

        assert validate_version_pins.main() == 1
        output = capsys.readouterr().out
        assert "bad pin" in output
        assert "warn" in output


def test_main_check_all_templates_ok(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = Path(validate_version_pins.__file__).parent.parent

    with TemporaryDirectory(dir=repo_root) as temp_dir:
        env_path = Path(temp_dir) / "autofix-versions.env"
        env_path.write_text("PYTEST_VERSION=7.0.0\n", encoding="utf-8")

        def fake_glob(self: Path, pattern: str) -> list[Path]:
            if self == repo_root and pattern == "templates/**/autofix-versions.env":
                return [env_path]
            return []

        monkeypatch.setattr(Path, "glob", fake_glob)
        monkeypatch.setattr(Path, "exists", lambda self: False)
        monkeypatch.setattr(
            validate_version_pins, "validate_file", lambda path: ([], [])
        )
        monkeypatch.setattr(
            validate_version_pins.sys,
            "argv",
            ["validate_version_pins.py", "--check-all-templates"],
        )

        assert validate_version_pins.main() == 0
        assert "OK" in capsys.readouterr().out


def test_main_check_all_templates_warnings_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = Path(validate_version_pins.__file__).parent.parent

    with TemporaryDirectory(dir=repo_root) as temp_dir:
        env_path = Path(temp_dir) / "autofix-versions.env"
        env_path.write_text("PYTEST_VERSION=7.0.0\n", encoding="utf-8")

        def fake_glob(self: Path, pattern: str) -> list[Path]:
            if self == repo_root and pattern == "templates/**/autofix-versions.env":
                return [env_path]
            return []

        def fake_exists(self: Path) -> bool:
            return str(self).endswith(".github/workflows/autofix-versions.env")

        monkeypatch.setattr(Path, "glob", fake_glob)
        monkeypatch.setattr(Path, "exists", fake_exists)
        monkeypatch.setattr(
            validate_version_pins, "validate_file", lambda path: ([], ["warn"])
        )
        monkeypatch.setattr(
            validate_version_pins.sys,
            "argv",
            ["validate_version_pins.py", "--check-all-templates"],
        )

        assert validate_version_pins.main() == 0
        output = capsys.readouterr().out
        assert "warning(s) - consider fixing" in output
