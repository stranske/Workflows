"""Minimal logger stub to satisfy script imports."""

from __future__ import annotations

import logging
import os
from typing import Optional


def setup_script_logging(
    name: str = "trend_analysis",
    *,
    module_file: Optional[str] = None,
    announce: bool = True,
) -> logging.Logger:
    """Set up logging for a script.

    Args:
        name: Logger name. If module_file is provided and name is default,
              the module name will be derived from the file path.
        module_file: Optional path to the module file (__file__). If provided,
                     the logger name will be derived from the file basename.
        announce: Whether to log a startup message (ignored in minimal stub).

    Returns:
        Configured logger instance.
    """
    # Derive name from module_file if provided and name is default
    if module_file is not None and name == "trend_analysis":
        name = os.path.splitext(os.path.basename(module_file))[0]

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
