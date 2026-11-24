# Recover the 11 original artifact metadata responses

The metadata archive contains the original GitHub API response files from the run 38118258124 recovery. Each file keeps its name and SHA-256 from [the original manifest](manifest.json). The artifact IDs, workflow run identities and metadata hashes remain in [the original recovery ledger](recovery.json).

From this evidence directory, run the block below. It prints the path of a scratch copy with the original manifest and every file it names. The original [ZIP recovery procedure](README.md) still describes the separately stored ZIPs and the limits of the offline diagnostic.

<!-- begin offline recovery -->
```sh
(
set -eu
source=$(cd "${EVIDENCE_DIR:-.}" && pwd -P)
scratch=$(mktemp -d "${TMPDIR:-/tmp}/issue-3820-metadata.XXXXXX")
archive="$source/artifact-metadata.tar.gz"
printf '%s  %s\n' b067f940537febcb8e2063da7b87b058e3e5ea544ef05f4ffc75ba28f3f794d0 "$archive" |
  shasum -a 256 -c
cp "$source/manifest.json" "$source/README.md" "$source/original-artifact-extraction.json" \
  "$source/patch-candidate.log" "$source/patch-mutation.json" "$source/patch-restored.log" \
  "$source/raw-console.tar.gz" "$source/recover-original-artifacts.py" "$source/recovery.json" "$scratch/"
tar -xzpf "$archive" -C "$scratch"
(
  cd "$scratch"
  jq -r 'to_entries[] | select(.value | type == "string") | "\(.value)  \(.key)"' manifest.json |
    shasum -a 256 -c
)
printf 'Recovered evidence: %s\n' "$scratch"
)
```
