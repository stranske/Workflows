from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class DiagnosticsRecorder:
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


@pytest.fixture()
def autofix_recorder() -> DiagnosticsRecorder:
    return DiagnosticsRecorder()
