#!/usr/bin/env python3
"""
Quick test script to verify OpenAI provider works.

Run this in GitHub Actions with OPENAI_API_KEY set:
    python scripts/test_openai_provider.py

Or locally with the key exported:
    export OPENAI_API_KEY="sk-..."
    python scripts/test_openai_provider.py
"""

import logging
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.llm_provider import check_providers, get_llm_provider

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_openai_provider() -> int:
    """Test that OpenAI provider is configured and working."""
    print("=" * 60)
    print("OpenAI Provider Test")
    print("=" * 60)

    # Check provider availability
    print("\nProvider availability:")
    availability = check_providers()
    for name, available in availability.items():
        status = "✓" if available else "✗"
        print(f"  {status} {name}")

    if not availability["openai"]:
        print("\n❌ OPENAI_API_KEY not set - cannot test OpenAI provider")
        return 1

    # Test OpenAI specifically
    print("\n" + "-" * 40)
    print("Testing OpenAI provider directly...")
    print("-" * 40)

    try:
        provider = get_llm_provider(force_provider="openai")
        print(f"Provider: {provider.name}")

        # Simple test analysis
        test_output = """
        I analyzed the codebase and found the issue.
        The bug was in the authentication module.
        I fixed the login validation logic.
        Tests are now passing.
        """
        test_tasks = ["Fix login bug", "Add unit tests"]

        print(f"\nTest tasks: {test_tasks}")
        print("Running analysis...")

        result = provider.analyze_completion(
            session_output=test_output,
            tasks=test_tasks,
        )

        print("\n✅ OpenAI provider working!")
        print(f"   Provider: {result.provider_used}")
        print(f"   Confidence: {result.confidence:.0%}")
        print(f"   Completed: {result.completed_tasks}")
        print(f"   In progress: {result.in_progress_tasks}")
        print(f"   Reasoning: {result.reasoning[:100]}...")

        return 0

    except Exception as e:
        print(f"\n❌ OpenAI provider failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(test_openai_provider())
