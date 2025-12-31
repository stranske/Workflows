import ast
import textwrap
from pathlib import Path

from scripts import mypy_return_autofix


def _expr(source: str) -> ast.AST:
    return ast.parse(source).body[0].value


def test_is_str_like_variants() -> None:
    assert mypy_return_autofix._is_str_like(_expr("'hello'"), set()) is True
    assert mypy_return_autofix._is_str_like(_expr('f"{value}"'), set()) is True
    assert mypy_return_autofix._is_str_like(_expr("name"), {"name"}) is True
    assert mypy_return_autofix._is_str_like(_expr("str(123)"), set()) is True
    assert mypy_return_autofix._is_str_like(_expr("'a'.upper()"), set()) is True
    assert mypy_return_autofix._is_str_like(_expr("'-'.join(['a'])"), set()) is True
    assert mypy_return_autofix._is_str_like(_expr("'hi {}'.format('x')"), set()) is True
    assert mypy_return_autofix._is_str_like(_expr("missing"), set()) is False


def test_is_list_of_str_variants() -> None:
    assert mypy_return_autofix._is_list_of_str(_expr("['a', 'b']"), set()) is True
    assert mypy_return_autofix._is_list_of_str(_expr("[1, 2]"), set()) is False
    assert mypy_return_autofix._is_list_of_str(_expr("names"), {"names"}) is True


def test_collect_string_vars_tracks_assignments() -> None:
    module = ast.parse(
        textwrap.dedent(
            """\
            def sample():
                greeting = "hi"
                alias = greeting
                names = ["a", f"{greeting}"]
                nums = [1]
                first, second = ["x", "y"]
            """
        )
    )
    func = module.body[0]
    string_vars, list_vars = mypy_return_autofix._collect_string_vars(func.body)

    assert string_vars == {"greeting", "alias"}
    assert list_vars == {"names", "nums"}


def test_process_function_updates_list_annotation() -> None:
    source = textwrap.dedent(
        """\
        def names() -> list[int]:
            items = ["a"]
            return items
        """
    )
    module = ast.parse(source)
    lines = source.splitlines()
    func = module.body[0]

    changed = mypy_return_autofix._process_function(func, lines, set())

    assert changed is True
    assert "list[str]" in lines[0]


def test_process_function_no_annotation_no_change() -> None:
    source = textwrap.dedent(
        """\
        def value():
            return "hi"
        """
    )
    module = ast.parse(source)
    lines = source.splitlines()
    func = module.body[0]

    changed = mypy_return_autofix._process_function(func, lines, set())

    assert changed is False


def test_process_function_skips_bare_return() -> None:
    source = textwrap.dedent(
        """\
        def value() -> int:
            return
        """
    )
    module = ast.parse(source)
    lines = source.splitlines()
    func = module.body[0]

    changed = mypy_return_autofix._process_function(func, lines, set())

    assert changed is False


def test_process_file_rewrites_annotation(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        textwrap.dedent(
            """\
            def value() -> int:
                return "hello"
            """
        ),
        encoding="utf-8",
    )

    assert mypy_return_autofix._process_file(path) is True
    assert "-> str:" in path.read_text(encoding="utf-8")


def test_annotation_to_str_without_unparse(monkeypatch) -> None:
    monkeypatch.delattr(ast, "unparse", raising=False)

    assert mypy_return_autofix._annotation_to_str(ast.Name(id="value")) == ""


def test_main_skips_missing_project_dirs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mypy_return_autofix, "ROOT", tmp_path)
    monkeypatch.setattr(mypy_return_autofix, "PROJECT_DIRS", [Path("missing")])

    assert mypy_return_autofix.main([]) == 0
