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

CRITICAL rules for split_suggestions:
- Each item MUST be a complete, independently understandable sentence
- Each item MUST be at least 5 words and start with an action verb
  (Create, Add, Update, Fix, Implement, Define, Test, Write, Configure)
- Do NOT split a sentence at commas into fragments
- Do NOT return single words, noun phrases, or sentence fragments
- BAD: ["methods", "input/output types", "metadata contract"]
- BAD: ["Update settings", "Fix bugs", "Add tests"]
- GOOD: ["Define the EmbeddingProvider interface with required methods",
         "Specify input and output types for each method",
         "Document the metadata contract between components"]

CRITICAL rules for content preservation:
- Do NOT duplicate sections that already exist in the issue body
- Do NOT repeat text that was already present under a different heading
- If a section already covers its topic, report it as present (NOT missing)

Output JSON with this shape:
{{
  "task_splitting": [{{"task": "...", "reason": "...", "split_suggestions": ["Complete actionable sub-task description"]}}],
  "blocked_tasks": [{{"task": "...", "reason": "...", "suggested_action": "..."}}],
  "objective_criteria": [{{"criterion": "...", "issue": "...", "suggestion": "..."}}],
  "missing_sections": ["Scope", "Implementation Notes"],
  "formatting_issues": ["..."],
  "overall_notes": "..."
}}
