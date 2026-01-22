from pathlib import Path


def test_agents_belt_scan_uses_retry_wrapper() -> None:
    script_path = Path('.github/scripts/agents_belt_scan.js')
    content = script_path.read_text(encoding='utf-8')

    assert 'withRetry' in content
    assert 'agents_belt_scan.list_pulls' in content
    assert 'agents_belt_scan.get_combined_status' in content
