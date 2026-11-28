from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / ".github/scripts/github-api-with-retry.js"


def _run_node(method: str, allow_non_idempotent: bool) -> dict[str, object]:
    if shutil.which("node") is None:
        pytest.skip("node is not available")

    script = f"""
const modulePath = {json.dumps(MODULE_PATH.as_posix())};
const {{ withRetry }} = require(modulePath);

(async () => {{
  let attempts = 0;
  console.log = () => {{}};
  console.error = () => {{}};
  try {{
    await withRetry(() => {{
      attempts += 1;
      if (attempts < 2) {{
        const err = new Error('fetch failed');
        err.status = 500;
        err.request = {{ method: {json.dumps(method)} }};
        throw err;
      }}
      return {{ headers: {{}} }};
    }}, {{ maxRetries: 1, initialDelay: 1, maxDelay: 1, allowNonIdempotentRetries: {str(allow_non_idempotent).lower()} }});
    process.stdout.write(JSON.stringify({{ attempts, caught: false }}));
  }} catch (error) {{
    process.stdout.write(JSON.stringify({{ attempts, caught: true }}));
  }}
}})();
"""

    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def test_transient_retry_get_is_idempotent() -> None:
    result = _run_node("GET", False)
    assert result["attempts"] == 2
    assert result["caught"] is False


def test_transient_retry_post_is_disabled_by_default() -> None:
    result = _run_node("POST", False)
    assert result["attempts"] == 1
    assert result["caught"] is True


def test_transient_retry_post_requires_opt_in() -> None:
    result = _run_node("POST", True)
    assert result["attempts"] == 2
    assert result["caught"] is False
