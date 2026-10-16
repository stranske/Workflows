"""Execute every managed guard parser against explicit enabled-field boundaries."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
START = "function routingLabelsFromRegistry(text) {"
END = "const PERMISSION_LABEL"


def parsers():
    result = []
    for prefix in (ROOT, ROOT / "templates/consumer-repo"):
        helper = prefix / ".github/scripts/agents-guard-fork-status-publication.js"
        source = helper.read_text()
        result.append(
            (str(helper.relative_to(ROOT)), source[source.index(START) : source.index(END)].strip())
        )
        workflow = prefix / ".github/workflows/agents-guard.yml"
        data = yaml.safe_load(workflow.read_text())
        for step in data["jobs"]["guard"]["steps"]:
            script = step.get("with", {}).get("script", "")
            if START in script:
                start = script.index(START)
                # All managed copies share the same final return/closing brace.
                end = script.index("\n}", start) + 2
                result.append((f"{workflow.relative_to(ROOT)}:{step['name']}", script[start:end]))
    assert len(result) == 8
    return result


CASES = [
    ("missing-eof", "agents:\n  first:\n", None),
    (
        "missing-next-agent",
        "agents:\n  first:\n    runner: example\n  second:\n    enabled: true\n",
        None,
    ),
    ("missing-next-section", "agents:\n  first:\n    runner: example\nother: value\n", None),
    ("missing-repeated-agents", "agents:\n  first:\nagents:\n  second:\n    enabled: true\n", None),
    ("nested-is-not-explicit", "agents:\n  first:\n    preflight:\n      enabled: true\n", None),
    (
        "nested-false-is-not-explicit",
        "agents:\n  first:\n    preflight:\n      enabled: false\n",
        None,
    ),
    ("duplicate-true", "agents:\n  first:\n    enabled: true\n    enabled: true\n", None),
    ("duplicate-conflict", "agents:\n  first:\n    enabled: false\n    enabled: true\n", None),
    (
        "duplicate-agent",
        "agents:\n  first:\n    enabled: true\n  first:\n    enabled: false\n",
        None,
    ),
    *[
        (f"invalid-{value}", f"agents:\n  first:\n    enabled: {value}\n", None)
        for value in ("", "yes", "True", "null", "1", '"true"', "[]")
    ],
    ("true-eof", "agents:\n  first:\n    enabled: true", ["agent:first"]),
    ("false-eof", "agents:\n  first:\n    enabled: false", []),
    (
        "explicit-survives-nested",
        "agents:\n  first:\n    enabled: true\n    preflight:\n      enabled: false\n  second:\n    enabled: false\n    preflight:\n      enabled: true\nother: value\n",
        ["agent:first"],
    ),
    (
        "comments-crlf",
        "agents:\r\n  first:\r\n    enabled: true # deliberate\r\n\r\n# end\r\n",
        ["agent:first"],
    ),
]


@pytest.mark.parametrize("surface,parser", parsers(), ids=lambda item: str(item)[:100])
@pytest.mark.parametrize("case,registry,expected", CASES, ids=[case[0] for case in CASES])
def test_enabled_contract_on_every_parser(surface, parser, case, registry, expected):
    harness = parser + """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
try { process.stdout.write(JSON.stringify({labels: [...routingLabelsFromRegistry(input)]})); }
catch(error) { process.stdout.write(JSON.stringify({error: error.message})); }
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps(registry),
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    if expected is None:
        assert "error" in result, (surface, case, result)
    else:
        assert "error" not in result, (surface, case, result)
        actual = sorted(
            set(result["labels"])
            - {"agent:auto", "agent:copilot", "agents:auto-pilot", "agents:keepalive"}
        )
        assert actual == expected


def test_shipped_registry_preserves_existing_enabled_routes():
    registries = [
        prefix / ".github/agents/registry.yml"
        for prefix in (ROOT, ROOT / "templates/consumer-repo")
    ]
    assert registries[0].read_bytes() == registries[1].read_bytes()
    for registry in registries:
        agents = yaml.safe_load(registry.read_text())["agents"]
        assert all(type(config.get("enabled")) is bool for config in agents.values())
        assert sorted(agent for agent, config in agents.items() if config["enabled"]) == [
            "claude",
            "codex",
            "cursor",
            "gemini",
            "muse",
        ]


def test_all_eight_parser_copies_are_byte_identical():
    assert len({parser for _, parser in parsers()}) == 1
