from __future__ import annotations

from scripts import auto_type_hygiene


def test_load_allowlist_defaults_when_missing_or_empty(monkeypatch):
    monkeypatch.delenv("AUTO_TYPE_ALLOWLIST", raising=False)
    assert auto_type_hygiene._load_allowlist() == auto_type_hygiene.DEFAULT_ALLOWLIST

    monkeypatch.setenv("AUTO_TYPE_ALLOWLIST", " , ")
    assert auto_type_hygiene._load_allowlist() == auto_type_hygiene.DEFAULT_ALLOWLIST

    monkeypatch.setenv("AUTO_TYPE_ALLOWLIST", "yaml, requests")
    assert auto_type_hygiene._load_allowlist() == ["yaml", "requests"]


def test_module_has_types_detects_fallback_stub_and_package(tmp_path, monkeypatch):
    assert auto_type_hygiene.module_has_types("yaml") is True

    stub_package = tmp_path / "pkg"
    stub_package.mkdir()
    (stub_package / "__init__.pyi").write_text("", encoding="utf-8")
    (tmp_path / "mod.pyi").write_text("", encoding="utf-8")
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [tmp_path])
    assert auto_type_hygiene.module_has_types("pkg") is True
    assert auto_type_hygiene.module_has_types("mod") is True

    package_dir = tmp_path / "foo"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "bar.py").write_text("", encoding="utf-8")
    typed_dir = tmp_path / "foo-stubs"
    typed_dir.mkdir()
    (typed_dir / "py.typed").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert auto_type_hygiene.module_has_types("foo.bar") is True

    assert auto_type_hygiene.module_has_types("no_such_module_123") is False


def test_has_stub_package_handles_sys_path_edge_cases(tmp_path, monkeypatch):
    existing = tmp_path / "exists"
    existing.mkdir()
    stub_dir = existing / "foo-stubs"
    stub_dir.mkdir()
    file_root = tmp_path / "file-root"
    file_root.mkdir()
    (file_root / "foo-stubs").write_text("", encoding="utf-8")
    missing = tmp_path / "missing"
    monkeypatch.setattr(
        auto_type_hygiene.sys,
        "path",
        [None, str(missing), str(file_root), str(existing)],
    )

    assert auto_type_hygiene._has_stub_package("foo") is False


def test_module_has_types_handles_spec_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [])

    def raise_error(_: str):
        raise ValueError("bad spec")

    monkeypatch.setattr(auto_type_hygiene.importlib.util, "find_spec", raise_error)
    assert auto_type_hygiene.module_has_types("oops") is False

    class FakeSpec:
        origin = "typed.pyi"
        submodule_search_locations = None

    monkeypatch.setattr(auto_type_hygiene.importlib.util, "find_spec", lambda _: FakeSpec())
    assert auto_type_hygiene.module_has_types("typed_mod") is True

    typed_dir = tmp_path / "typed"
    typed_dir.mkdir()
    (typed_dir / "py.typed").write_text("", encoding="utf-8")

    class SearchSpec:
        origin = "file.py"
        submodule_search_locations = [str(typed_dir)]

    monkeypatch.setattr(auto_type_hygiene.importlib.util, "find_spec", lambda _: SearchSpec())
    assert auto_type_hygiene.module_has_types("search_mod") is True

    class EmptySearchSpec:
        origin = "file.py"
        submodule_search_locations = [None]

    monkeypatch.setattr(auto_type_hygiene, "_has_stub_package", lambda _: False)
    monkeypatch.setattr(auto_type_hygiene.importlib.util, "find_spec", lambda _: EmptySearchSpec())
    assert auto_type_hygiene.module_has_types("empty_search") is False


def test_needs_ignore_respects_allowlist_and_types(monkeypatch):
    monkeypatch.setattr(auto_type_hygiene, "ALLOWLIST", ["foo"])
    monkeypatch.setattr(auto_type_hygiene, "module_has_types", lambda module: False)
    assert auto_type_hygiene.needs_ignore("foo") is True
    assert auto_type_hygiene.needs_ignore("bar") is False

    monkeypatch.setattr(auto_type_hygiene, "module_has_types", lambda module: True)
    assert auto_type_hygiene.needs_ignore("foo") is False


def test_process_file_handles_ignore_injections(tmp_path, monkeypatch):
    path = tmp_path / "sample.py"
    path.write_text(
        "\n".join(
            [
                "print('hi')",
                "import foo",
                "import foo  # type: ignore[]",
                "from foo import bar  # type: ignore",
                "import foo  # type: ignore[import-untyped]",
                "import foo  # type: ignore[unused-ignore, import-untyped]",
                "import foo  # type: ignore[import-untyped, unused-ignore]",
                "import bar",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(auto_type_hygiene, "needs_ignore", lambda module: module == "foo")
    changed, new_lines = auto_type_hygiene.process_file(path)

    assert changed is True
    assert new_lines[0] == "print('hi')"
    assert new_lines[1].endswith(auto_type_hygiene.IGNORE_TOKEN)
    assert new_lines[2].endswith(auto_type_hygiene.IGNORE_TOKEN)
    assert new_lines[3].endswith(auto_type_hygiene.IGNORE_TOKEN)
    assert new_lines[4].endswith(auto_type_hygiene.IGNORE_TOKEN)
    assert new_lines[5] == "import foo  # type: ignore[unused-ignore, import-untyped]"
    assert new_lines[6] == "import foo  # type: ignore[import-untyped, unused-ignore]"
    assert new_lines[7] == "import bar"


def test_process_file_missing_file_returns_no_change(tmp_path):
    missing = tmp_path / "missing.py"
    changed, new_lines = auto_type_hygiene.process_file(missing)
    assert changed is False
    assert new_lines == []


def test_iter_python_files_skips_excluded_paths(tmp_path, monkeypatch):
    keep = tmp_path / "ok.py"
    keep.write_text("print('ok')\n", encoding="utf-8")

    (tmp_path / "archives" / "legacy_assets").mkdir(parents=True)
    (tmp_path / "archives" / "legacy_assets" / "skip.py").write_text("", encoding="utf-8")
    (tmp_path / "Old").mkdir()
    (tmp_path / "Old" / "skip.py").write_text("", encoding="utf-8")
    (tmp_path / "notebooks" / "old").mkdir(parents=True)
    (tmp_path / "notebooks" / "old" / "skip.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [tmp_path / "missing", tmp_path])
    files = list(auto_type_hygiene.iter_python_files())

    assert files == [keep]


def test_main_dry_run_reports_changes(tmp_path, monkeypatch, capsys):
    module_root = tmp_path / "repo"
    module_root.mkdir()
    file_path = module_root / "sample.py"
    file_path.write_text("import foo\n", encoding="utf-8")

    monkeypatch.setattr(auto_type_hygiene, "ROOT", module_root)
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [module_root])
    monkeypatch.setattr(auto_type_hygiene, "DRY_RUN", True)
    monkeypatch.setattr(auto_type_hygiene, "needs_ignore", lambda module: True)

    exit_code = auto_type_hygiene.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Added import-untyped ignores" in output
    assert file_path.read_text(encoding="utf-8") == "import foo\n"


def test_main_reports_no_changes(tmp_path, monkeypatch, capsys):
    module_root = tmp_path / "repo"
    module_root.mkdir()
    file_path = module_root / "sample.py"
    file_path.write_text("import foo\n", encoding="utf-8")

    monkeypatch.setattr(auto_type_hygiene, "ROOT", module_root)
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [module_root])
    monkeypatch.setattr(auto_type_hygiene, "DRY_RUN", False)
    monkeypatch.setattr(auto_type_hygiene, "needs_ignore", lambda module: False)

    exit_code = auto_type_hygiene.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert output.strip() == "[auto_type_hygiene] No changes needed."
    assert file_path.read_text(encoding="utf-8") == "import foo\n"


def test_main_writes_changes(tmp_path, monkeypatch):
    module_root = tmp_path / "repo"
    module_root.mkdir()
    file_path = module_root / "sample.py"
    file_path.write_text("import foo\n", encoding="utf-8")

    monkeypatch.setattr(auto_type_hygiene, "ROOT", module_root)
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [module_root])
    monkeypatch.setattr(auto_type_hygiene, "DRY_RUN", False)
    monkeypatch.setattr(auto_type_hygiene, "needs_ignore", lambda module: True)

    exit_code = auto_type_hygiene.main()

    assert exit_code == 0
    assert auto_type_hygiene.IGNORE_TOKEN in file_path.read_text(encoding="utf-8")
