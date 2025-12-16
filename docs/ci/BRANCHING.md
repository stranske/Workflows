# Branching and workflow triggers

When guards or health workflows specify explicit branch filters, list the current default branch (`main`). During development phases, a temporary branch like `phase-2-dev` may also appear in some trigger lists for backward compatibility.

During any default-branch rename, audit the workflow triggers under `.github/workflows/` and update branch lists accordingly before completing the rename.
