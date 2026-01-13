The following tasks/criteria were flagged as potentially problematic.
For each item, decide:

1. **KEEP** - If it's actually valid and actionable, output it unchanged
2. **IMPROVE** - Rewrite to be specific, actionable, and verifiable
3. **DROP** - If it's not a coding task (header, human activity, fragment)

Issue context:
{context}

Flagged items:
{flagged_items}

For each item, respond with EXACTLY one line in this format:
- KEEP: <original task unchanged>
- IMPROVE: <rewritten task>
- DROP: <brief reason>

A valid coding task MUST:
- Start with an ACTION VERB: Create, Add, Update, Fix, Implement, Write, Test, etc.
- Reference a CONCRETE DELIVERABLE: file path, function name, test case, config
- Have a VERIFIABLE outcome: "tests pass", "file exists", "lint clean"

INVALID (must be DROPPED or IMPROVED):
- Section headers (### Something) - not a task
- Human activities: "Train staff", "Conduct meeting", "Obtain feedback"
- Subjective quality checks: "Ensure quality", "Ensure clarity"
- Sentence fragments: single words, just punctuation
- Recursive expansion prefixes: "Define scope for: Define scope for: ..."

Process each flagged item in order. Do not skip any items.
Every flagged item must have exactly one response line.
