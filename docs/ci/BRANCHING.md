# Branching and workflow triggers

When guards or health workflows specify explicit branch filters, list the current default branch (`main`). Retired development branches must not remain in live trigger lists or operator examples.

During any default-branch rename, audit the workflow triggers under `.github/workflows/` and update branch lists accordingly before completing the rename.
