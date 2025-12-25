I couldn’t locate any failing job details in the repo, and the run context says the workflow was cancelled with no failing jobs reported. There are no local logs beyond `autofix_report_enriched.json`, so there’s nothing concrete to fix in this workspace.

If you want me to proceed, I’ll need one of these:
1) Paste the relevant CI log excerpt for the failing job(s).
2) Re-run the workflow and share the failing job name + error snippet.

If you just want a quick local check, you can run `pytest -q` and share any failures.