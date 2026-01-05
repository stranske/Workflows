from __future__ import annotations

from scripts.langchain import task_decomposer


def test_decompose_task_fallback_adds_verification() -> None:
    result = task_decomposer.decompose_task("Update docs and add tests", use_llm=False)
    sub_tasks = result["sub_tasks"]
    assert len(sub_tasks) >= 2
    assert all("verify" in task.lower() for task in sub_tasks)


def test_normalize_subtasks_splits_multi_action() -> None:
    sub_tasks = task_decomposer._normalize_subtasks(["Update docs and add tests"])
    assert len(sub_tasks) == 2
    assert any("update docs" in task.lower() for task in sub_tasks)
    assert any("add tests" in task.lower() for task in sub_tasks)
    assert all("verify" in task.lower() for task in sub_tasks)
    assert any("docs updated" in task.lower() for task in sub_tasks)
    assert any("tests pass" in task.lower() for task in sub_tasks)


def test_normalize_subtasks_strips_dependency_clause() -> None:
    sub_tasks = task_decomposer._normalize_subtasks(["After merging PR #123, update docs"])
    assert len(sub_tasks) == 1
    assert "after merging" not in sub_tasks[0].lower()
    assert "update docs" in sub_tasks[0].lower()


def test_normalize_subtasks_rephrases_dependency_phrases() -> None:
    sub_tasks = task_decomposer._normalize_subtasks(["Depends on backend merge"])
    assert len(sub_tasks) == 1
    assert sub_tasks[0].lower().startswith("document dependency for:")
    assert "depends on" not in sub_tasks[0].lower()
    assert "verify" in sub_tasks[0].lower()


def test_normalize_subtasks_scopes_large_tasks() -> None:
    sub_tasks = task_decomposer._normalize_subtasks(
        ["Implement end-to-end workflow for keepalive metrics collection"]
    )
    assert len(sub_tasks) == 3
    assert any(task.lower().startswith("define scope for:") for task in sub_tasks)
    assert any(task.lower().startswith("implement focused slice for:") for task in sub_tasks)
    assert any(task.lower().startswith("validate focused slice for:") for task in sub_tasks)
    assert all("verify" in task.lower() for task in sub_tasks)
