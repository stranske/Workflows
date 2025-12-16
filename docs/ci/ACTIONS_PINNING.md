# Actions Pinning Guide

Pin third-party GitHub Actions by commit SHA so security regressions or tag
retags cannot silently change workflow behaviour. Start with the Gate pipeline,
branch-protection audits, and PR meta manager workflows because they run on
nearly every pull request.

## Updating a pinned action

1. Locate the release tag you want to adopt (for example, `v3`).
2. Resolve the tag to its commit SHA.
3. Replace the existing `uses:` reference with the SHA and append an inline
   comment noting the human-friendly tag.
4. Re-run the affected workflow(s) to confirm they still succeed.

The following shell snippet automates steps 1–3. Replace `{owner}` and
`{repo}` with the action source and set `TAG` to the desired release.

```bash
OWNER="dorny"
REPO="paths-filter"
TAG="v3"
SHA=$(gh api repos/${OWNER}/${REPO}/git/ref/tags/${TAG} --jq '.object.sha')
# Annotated tags require a second hop to resolve to the commit object.
TYPE=$(gh api repos/${OWNER}/${REPO}/git/ref/tags/${TAG} --jq '.object.type')
if [ "${TYPE}" = "tag" ]; then
  SHA=$(gh api repos/${OWNER}/${REPO}/git/tags/${SHA} --jq '.object.sha')
fi
echo "Pin ${OWNER}/${REPO}@${TAG} -> ${SHA}"
```

Update the workflow reference with
`${OWNER}/${REPO}@${SHA} # ${TAG}`. Commit the change and document the
bump in the pull request summary.

## When to update

- Security advisories or workflow failures that cite the action.
- Required features or bug fixes released in a newer tag.
- Quarterly maintenance: audit all pinned SHAs and refresh them to the latest
  stable tag.

Document the reasoning in the associated issue or pull request so future audits
understand why the pin changed.
