# Retained canary input replay

These are public retained inputs from Orchestrator PR984, Verify run40597948352.
`SOURCE.json` records the original context/diff and three CI archive hashes.
The archive metadata refers to a separate read-only native replay from run40587242679 at exact head
`0507d28acf68d6bf21c68138d18d56cd01968827`; their ZIP SHA256 values match the
original context inventory. The raw CI ZIPs and their unrelated reports are not
copied into this source fixture. Minimal native SQLite and actual ZIP/CRC tests
are generated inertly; retained context/diff are data and never executed.

The original native Verify returned UNVERIFIABLE_INPUT with used_llm=false.
The Python test changes only the collector-owned typed failure classification
in an in-memory context copy. The Node tests prove that this classification
requires safe coverage.py sidecar names and bounded, CRC-checked native SQLite
format bytes plus an isolated, bounded, immutable read-only SQLite quick_check.
Missing runtimes and failed checks retain unsupported/integrity status.
Resource-bound failures remain recorded and all limits are
unchanged. The modeled FAIL response proves admission and preservation only;
it is not a new native canary assessment or a claim that the CSV task is complete.

Explicit selected proof, corrupt ZIPs, duplicate or unsafe names, unknown binary
payloads and malformed/header-only SQLite remain blocking. SQLite format
recognition is not proof that database contents are correct or fulfill a task.
