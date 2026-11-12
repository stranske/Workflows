import importlib.util
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "health", Path(__file__).parents[1] / "scripts/langsmith_observability_health.py"
)
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)
NOW = datetime(2026, 11, 12, tzinfo=UTC)


class SmithDBMigrationTests(unittest.TestCase):

    def query(self, endpoint="https://api.smith.langchain.com"):
        return health.query_latest_trace(
            api_key="synthetic-key",
            endpoint=endpoint,
            project="workflows-agents",
            now=NOW,
            search_hours=168,
        )

    def test_v2_body_pages_and_latest(self):
        calls = []

        def request(method, url, **kwargs):
            body = dict(kwargs.get("body") or {})
            calls.append((method, url, body))
            if method == "GET":
                return [
                    {"name": "other", "id": "wrong"},
                    {"name": "workflows-agents", "id": "project"},
                ]
            if "cursor" not in body:
                return {
                    "items": [
                        {"id": "old", "start_time": "2026-11-10T00:00:00Z"},
                        {"id": "invalid"},
                    ],
                    "next_cursor": "next",
                }
            return {
                "items": [{"id": "latest", "start_time": "2026-11-11T23:00:00Z"}],
                "next_cursor": None,
            }

        with patch.object(health, "_request_json", request):
            assert self.query()["id"] == "latest"
        assert calls[1][1] == "https://api.smith.langchain.com/api/v2/runs/query"
        assert calls[1][2] == {
            "project_ids": ["project"],
            "min_start_time": "2026-11-05T00:00:00+00:00",
            "max_start_time": NOW.isoformat(),
            "selects": ["ID", "TRACE_ID", "START_TIME", "STATUS"],
            "page_size": 100,
        }
        assert calls[2][2]["cursor"] == "next"

    def test_v1_base_empty_results(self):
        with patch.object(
            health,
            "_request_json",
            side_effect=[[{"name": "workflows-agents", "id": "project"}], {"items": []}],
        ) as request:
            assert self.query("https://api.smith.langchain.com/api/v1") is None
        assert request.call_args.args[1] == "https://api.smith.langchain.com/api/v2/runs/query"

    def test_old_shape_is_error_not_false_no_traces(self):
        with (
            patch.object(
                health,
                "_request_json",
                side_effect=[[{"name": "workflows-agents", "id": "project"}], {"runs": []}],
            ),
            self.assertRaisesRegex(RuntimeError, "invalid items"),
        ):
            self.query()

    def test_repeated_cursor_fails(self):
        with (
            patch.object(
                health,
                "_request_json",
                side_effect=[
                    [{"name": "workflows-agents", "id": "project"}],
                    {"items": [], "next_cursor": "repeat"},
                    {"items": [], "next_cursor": "repeat"},
                ],
            ),
            self.assertRaisesRegex(RuntimeError, "repeated cursor"),
        ):
            self.query()


if __name__ == "__main__":
    unittest.main()
