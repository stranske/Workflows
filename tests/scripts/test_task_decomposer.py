from __future__ import annotations

from scripts.langchain import task_decomposer


def test_decompose_task_fallback_adds_verification() -> None:
    result = task_decomposer.decompose_task("Update docs and add tests", use_llm=False)
    sub_tasks = result["sub_tasks"]
    assert len(sub_tasks) >= 2
    assert all("verify" in task.lower() for task in sub_tasks)
