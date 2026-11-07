"""Break-and-revert driver for issue 4019 r3 (run from repo root).

Each mutation applies exact source replacements, runs ONE test node (must fail),
restores the original bytes (sha256 checked), and reruns it (must pass).
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PY = sys.executable
AGG = "scripts/aggregate_agent_metrics.py"
LLM = "tools/llm_provider.py"
TA = "tests/scripts/test_aggregate_agent_metrics.py::"
TL = "tests/tools/test_llm_provider.py::TestRemainingProviderPaths::"

# (id, node, file, old, new, expected_count)
MUTATIONS = [
    (
        "01",
        TA + "test_langsmith_trace_refs_skip_trace_list_item_without_id_or_url",
        AGG,
        "            elif item_trace_url:",
        "            else:",
        1,
    ),
    (
        "02",
        TA + "test_autopilot_summary_ignores_step_with_unknown_success_value",
        AGG,
        '        elif success in (False, "false", "False", "0", 0):',
        "        else:",
        1,
    ),
    (
        "03",
        TA + "test_codex_freshness_summary_tolerates_missing_update_targets",
        AGG,
        '        targets = entry.get("update_targets")\n        if isinstance(targets, list):',
        '        targets = entry.get("update_targets")\n        if True:',
        1,
    ),
    (
        "04",
        TL + "test_configured_model_falls_back_when_registry_import_fails",
        LLM,
        "    except ImportError:\n        return fallback\n",
        '    except ImportError:\n        return ""\n',
        1,
    ),
    (
        "05",
        TL + "test_metadata_keeps_explicit_issue_or_pr_number",
        LLM,
        "    if issue_or_pr_number is None:",
        "    if True:",
        1,
    ),
    (
        "06",
        TL + "test_extract_trace_id_uses_instance_dict_when_id_attribute_hidden",
        LLM,
        '            if "id" in response_dict:',
        "            if False:",
        1,
    ),
    (
        "07",
        TL + "test_extract_trace_id_returns_none_when_metadata_access_raises",
        LLM,
        '    except Exception as e:\n        logger.debug(f"Failed to extract trace ID',
        '    except KeyError as e:\n        logger.debug(f"Failed to extract trace ID',
        1,
    ),
    (
        "08",
        TL + "test_base_supports_quality_context_false_when_signature_unavailable",
        LLM,
        '        except (TypeError, ValueError):\n            return False\n        return "quality_context"',
        '        except (TypeError, ValueError):\n            return True\n        return "quality_context"',
        1,
    ),
    (
        "09",
        TL + "test_supports_quality_context_error_falls_back_to_legacy_signature",
        LLM,
        "    elif supports is not None:",
        "    if supports is not None:",
        1,
    ),
    (
        "10",
        TL + "test_supports_quality_context_without_helper_uses_signature",
        LLM,
        '    return "quality_context" in parameters or any(\n        param.kind',
        "    return True or any(\n        param.kind",
        1,
    ),
    (
        "11",
        TL + "test_github_client_none_when_langchain_openai_missing",
        LLM,
        '        except ImportError:\n            logger.warning("langchain_openai not installed")',
        '        except KeyError:\n            logger.warning("langchain_openai not installed")',
        1,
    ),
    (
        "12",
        TL + "test_github_client_none_without_reviewed_model",
        LLM,
        '        if not model_name:\n            logger.warning("No reviewed GitHub Models',
        '        if False:\n            logger.warning("No reviewed GitHub Models',
        1,
    ),
    (
        "13",
        TL + "test_github_client_targets_github_models_endpoint",
        LLM,
        "            base_url=GITHUB_MODELS_BASE_URL,",
        "            base_url=None,",
        1,
    ),
    (
        "14",
        TL + "test_github_analyze_requires_client",
        LLM,
        '        if not client:\n            raise RuntimeError(\n                "GitHub Models client',
        '        if False:\n            raise RuntimeError(\n                "GitHub Models client',
        1,
    ),
    (
        "15",
        TL + "test_github_analyze_reraises_api_error",
        LLM,
        '            logger.error(f"GitHub Models API error: {e}")\n            raise',
        '            logger.error(f"GitHub Models API error: {e}")\n            return None',
        1,
    ),
    (
        "16",
        TL + "test_langchain_client_none_when_helper_missing",
        LLM,
        '        except ImportError:\n            logger.warning("LangChain client helper not available")',
        '        except KeyError:\n            logger.warning("LangChain client helper not available")',
        2,
    ),
    (
        "17",
        TL + "test_langchain_client_none_when_build_returns_nothing",
        LLM,
        "        if resolved:\n            self._model_name = resolved.model",
        "        if True:\n            self._model_name = resolved.model",
        2,
    ),
    (
        "18",
        TL + "test_openai_analyze_reraises_api_error",
        LLM,
        '            logger.error(f"OpenAI API error: {e}")\n            raise',
        '            logger.error(f"OpenAI API error: {e}")\n            return None',
        1,
    ),
    (
        "19",
        TL + "test_anthropic_does_not_retry_unrelated_type_error",
        LLM,
        '                    if "quality_context" not in message:\n                        raise',
        "                    if False:\n                        raise",
        1,
    ),
    (
        "20",
        TL + "test_fallback_chain_name_before_any_attempt",
        LLM,
        '        return "fallback-chain"\n',
        '        return "fallback-chain()"\n',
        1,
    ),
    (
        "21",
        TL + "test_fallback_chain_reports_no_available_providers",
        LLM,
        '        raise RuntimeError("No providers available")',
        '        raise RuntimeError("All providers failed")',
        1,
    ),
    (
        "22a",
        TL + "test_fallback_chain_does_not_retry_unrelated_type_error",
        LLM,
        "                if not self._is_quality_context_type_error(exc):\n                    raise",
        "                if False:\n                    raise",
        1,
    ),
    (
        "22b",
        TL + "test_fallback_chain_does_not_retry_unrelated_type_error",
        LLM,
        '        if "quality_context" not in message:\n            return False',
        '        if "quality_context" not in message:\n            return True',
        1,
    ),
    (
        "23a",
        TL + "test_subscription_provider_unavailable_paths",
        LLM,
        'else "subscription-unavailable"',
        'else "subscription"',
        1,
    ),
    (
        "23b",
        TL + "test_subscription_provider_unavailable_paths",
        LLM,
        '        if self.resolved is None:\n            raise RuntimeError("Subscription analysis CLI unavailable")',
        '        if False:\n            raise RuntimeError("Subscription analysis CLI unavailable")',
        1,
    ),
    (
        "23c",
        TL + "test_subscription_provider_unavailable_paths",
        LLM,
        '            raise RuntimeError("Subscription analysis CLI/auth unavailable; no API fallback")',
        "            pass",
        1,
    ),
    (
        "24",
        TL + "test_forced_available_provider_is_returned_directly",
        LLM,
        '        logger.info(f"Using forced provider: {force_provider}")\n        return provider',
        '        logger.info(f"Using forced provider: {force_provider}")\n'
        "        return FallbackChainProvider([provider])",
        1,
    ),
]


def run(node: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", node, "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main(out_dir: Path) -> int:
    receipts = []
    ok = True
    for mid, node, path, old, new, count in MUTATIONS:
        src = Path(path)
        original = src.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        text = original.decode()
        assert text.count(old) == count, (mid, text.count(old))
        try:
            src.write_text(text.replace(old, new))
            red_code, red_out = run(node)
        finally:
            src.write_bytes(original)
        restored = hashlib.sha256(src.read_bytes()).hexdigest()
        green_code, green_out = run(node)
        cmd = f"{PY} -m pytest {node} -q -p no:cacheprovider"
        (out_dir / f"{mid}-red.txt").write_text(f"$ {cmd}\n{red_out}exit={red_code}\n")
        (out_dir / f"{mid}-green.txt").write_text(f"$ {cmd}\n{green_out}exit={green_code}\n")
        passed = red_code == 1 and "FAILED" in red_out and green_code == 0 and restored == digest
        ok &= passed
        receipts.append(
            {
                "id": mid,
                "node": node,
                "file": path,
                "replace": old,
                "with": new,
                "occurrences": count,
                "red_exit": red_code,
                "green_exit": green_code,
                "red_last_line": red_out.strip().splitlines()[-1],
                "green_last_line": green_out.strip().splitlines()[-1],
                "sha256_before": digest,
                "sha256_restored": restored,
                "proof_ok": passed,
            }
        )
        print(mid, "red", red_code, "green", green_code, "ok" if passed else "NOT OK")
    (out_dir / "mutation-receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
