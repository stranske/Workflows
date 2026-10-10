"""Native capacity capabilities for response/coverage unit-test clients (no network)."""

from types import SimpleNamespace
from unittest import mock


def with_capacity(client):
    client._unit_capacity_fake = True
    client.profile = {"max_input_tokens": 1_000_000, "max_output_tokens": 4096}
    client.max_tokens = 4096
    client._get_request_payload = lambda prompt: {
        "model": "unit-test-model",
        "input": [{"role": "user", "content": prompt}],
        "max_output_tokens": 4096,
    }
    client.root_client = SimpleNamespace(
        responses=SimpleNamespace(
            input_tokens=SimpleNamespace(
                count=mock.Mock(return_value=SimpleNamespace(input_tokens=1000))
            )
        )
    )
    return client
