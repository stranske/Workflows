"""Reject missing, stale and broken active PyYAML runtimes before repair selection."""

import importlib
import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.mark.parametrize("health", ["missing", "stale", "broken", "healthy"])
def test_active_runtime_health_requires_distribution_version_and_real_import(
    tmp_path, monkeypatch, helper, health
):
    namespace = helper["_pyyaml_runtime_needs_repair"].__globals__
    imported = tmp_path / "imported"
    name = f"private_yaml_health_{health}"
    module = tmp_path / f"{name}.py"
    module.write_text(
        "from pathlib import Path\n"
        f"Path({str(imported)!r}).write_text('attempted')\n"
        + ("raise ImportError('private YAML runtime is broken')\n" if health == "broken" else ""),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, name, raising=False)
    calls = []
    import_results = []

    def version(distribution):
        calls.append(("version", distribution))
        if health == "missing":
            raise namespace["metadata"].PackageNotFoundError(distribution)
        return "5.4.1" if health == "stale" else "6.0.3"

    def real_import(requested):
        calls.append(("import", requested))
        try:
            result = importlib.import_module(name)
        except ImportError as error:
            import_results.append(error)
            raise
        import_results.append(result)
        return result

    monkeypatch.setattr(namespace["metadata"], "version", version)
    monkeypatch.setitem(namespace, "import_module", real_import)

    try:
        assert helper["_pyyaml_runtime_needs_repair"]() is (health != "healthy")
        assert calls == [("version", "PyYAML")] + (
            [("import", "yaml")] if health in {"broken", "healthy"} else []
        )
        assert imported.exists() is (health in {"broken", "healthy"})
        if imported.exists():
            assert imported.read_text() == "attempted"
        if health == "healthy":
            assert len(import_results) == 1
            assert import_results[0] is sys.modules[name]
            assert Path(import_results[0].__file__) == module
        elif health == "broken":
            assert len(import_results) == 1
            assert isinstance(import_results[0], ImportError)
            assert str(import_results[0]) == "private YAML runtime is broken"
            assert name not in sys.modules
        else:
            assert import_results == []
            assert name not in sys.modules
    finally:
        # A successful real import must not leak this temporary module to later tests.
        sys.modules.pop(name, None)
