Analyze this issue for agent compatibility and formatting quality.

Issue body:
{issue_body}

Identify:
1. Tasks that are too broad (should be split)
2. Tasks the agent cannot complete (use AGENT_LIMITATIONS)
3. Subjective acceptance criteria (suggest objective alternatives)
4. Missing sections (why, scope, non-goals, implementation notes)
5. Formatting issues (bullets used for non-tasks, etc.)

AGENT_LIMITATIONS:
{agent_limitations}

Output JSON with this shape:
{{
  "task_splitting": [{{"task": "...", "reason": "...", "split_suggestions": ["..."]}}],
  "blocked_tasks": [{{"task": "...", "reason": "...", "suggested_action": "..."}}],
  "objective_criteria": [{{"criterion": "...", "issue": "...", "suggestion": "..."}}],
  "missing_sections": ["Scope", "Implementation Notes"],
  "formatting_issues": ["..."],
  "overall_notes": "..."
}}
