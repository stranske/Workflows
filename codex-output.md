I’m blocked by the repo security rules: every remaining task requires edits under `.github/workflows/**` or `.github/scripts/**`, which are explicitly forbidden in `agent-standard`. The first task (pipeline validation via a test PR + workflow logs) is also not something I can perform from here.

To proceed, I need one of these:
1) Run with `agent-high-privilege` so I can edit the workflow/script files and implement the tasks.
2) You (or a human) make the required changes; I can then validate/iterate.

If you want, I can list the exact files to change and the edits needed once you confirm which path you prefer.