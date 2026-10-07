"""Check the required Black source set serially and populate its writable cache."""

import tomllib
from pathlib import Path

import black


def main():
    root = Path.cwd()
    config = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["black"]
    report = black.Report(check=True)
    sources = black.get_sources(
        root=root,
        src=(".",),
        quiet=False,
        verbose=False,
        include=black.re_compile_maybe_verbose(config["include"]),
        exclude=black.re_compile_maybe_verbose(r"(\.workflows-lib|node_modules)"),
        extend_exclude=black.re_compile_maybe_verbose(config["extend-exclude"]),
        force_exclude=None,
        report=report,
        stdin_filename=None,
    )
    mode = black.Mode(
        target_versions={black.TargetVersion[name.upper()] for name in config["target-version"]},
        line_length=100,
    )
    for source in sorted(sources):
        black.reformat_one(
            source, fast=False, write_back=black.WriteBack.CHECK, mode=mode, report=report
        )
    print(report)
    raise SystemExit(report.return_code)


if __name__ == "__main__":
    main()
