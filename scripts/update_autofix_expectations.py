"""Update expectation constants based on callable outputs."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(".")


@dataclass(frozen=True)
class AutofixTarget:
    module: str
    callable_name: str
    constant_name: str


TARGETS: tuple[AutofixTarget, ...] = ()


def _update_constant(module, target: AutofixTarget) -> bool:
    func = getattr(module, target.callable_name, None)
    if func is None:
        print("No expectation updates applied")
        return False

    expected_value = func()
    module_path = Path(module.__file__ or "")
    if not module_path.exists():
        return False

    lines = module_path.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    changed = False
    prefix = f"{target.constant_name} ="
    for line in lines:
        if line.startswith(prefix):
            new_lines.append(f"{target.constant_name} = {expected_value!r}")
            changed = True
        else:
            new_lines.append(line)

    if changed:
        module_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return changed


def main(_args: list[str] | None = None) -> int:
    for target in TARGETS:
        module = importlib.import_module(target.module)
        _update_constant(module, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
