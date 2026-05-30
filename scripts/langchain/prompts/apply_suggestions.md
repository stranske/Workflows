Apply the approved suggestions to this already-structured issue as a PATCH.

The issue is ALREADY in AGENT_ISSUE_TEMPLATE form. Your job is to apply ONLY the
listed suggestions — NOT to re-format, re-paraphrase, re-order, or re-derive the
issue. This is the single most important rule: re-writing already-good content is
what makes issues balloon.

Current issue body:
{original_body}

Approved suggestions:
{suggestions_json}

Rules:
- Change ONLY the specific tasks/criteria/sections named in the suggestions.
- Preserve ALL other text VERBATIM, including the existing section structure and
  the trailing "<details>Original Issue</details>" block.
- Apply each task split in place (replace the one task with its named sub-tasks);
  do not also restate the parent.
- Move blocked tasks to a "## Deferred Tasks (Requires Human)" section (create it
  once if absent; never duplicate it).

CRITICAL - Length & Scope Discipline:
- Do NOT increase total length except by the minimum needed to apply a suggestion.
- Do NOT invent file paths, function names, tests, or acceptance criteria the
  source does not imply, and do NOT fill empty/placeholder sections with
  manufactured prose.
- Never restate the same point under two headings.

When a suggestion DOES add or rewrite a task, that task must be ACTIONABLE:
- Start with a CODING ACTION VERB: Create, Add, Update, Fix, Implement, Write, Test
- Reference CONCRETE DELIVERABLES already implied by the source
- Be completable by a coding agent in ~10 minutes
- NEVER turn section headers (### Something) into checkbox tasks
- NEVER include human-only activities: "Train staff", "Conduct meeting"

When a suggestion DOES add or rewrite an acceptance criterion, it must be
VERIFIABLE:
- Have MEASURABLE outcomes: "tests pass", "file exists", "lint passes"
- AVOID subjective language: "clean", "nice", "quality", "properly"

Output the full issue body with the suggestions applied and everything else
unchanged.
