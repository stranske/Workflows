#!/usr/bin/env bash
# Sync GitHub Action versions from .github/workflows/ to templates/
# Run this after Dependabot updates are merged to keep templates in sync.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

# Extract versions from .github/workflows/
declare -A versions

echo "Extracting versions from .github/workflows/..."
for file in .github/workflows/*.yml; do
    while IFS= read -r line; do
        if [[ "$line" =~ uses:[[:space:]]*([^[:space:]]+)@(v[0-9]+) ]]; then
            action="${BASH_REMATCH[1]}"
            version="${BASH_REMATCH[2]}"
            # Use numeric comparison for versions
            if [[ -z "${versions[$action]:-}" ]]; then
                versions["$action"]="$version"
            else
                new_num="${version#v}"
                current_num="${versions[$action]#v}"
                if (( new_num > current_num )); then
                    versions["$action"]="$version"
                fi
            fi
        fi
    done < "$file"
done

echo ""
echo "Detected versions:"
for action in "${!versions[@]}"; do
    echo "  $action: ${versions[$action]}"
done

checkout="${versions[actions/checkout]:-v4}"
github_script="${versions[actions/github-script]:-v7}"
upload_artifact="${versions[actions/upload-artifact]:-v4}"
download_artifact="${versions[actions/download-artifact]:-v4}"
cache="${versions[actions/cache]:-v4}"

echo ""
echo "Updating templates/..."

# Update templates
find templates/ -name "*.yml" -type f | while read -r file; do
    orig=$(cat "$file")
    
    sed -i \
        -e "s|actions/checkout@v[0-9]\+|actions/checkout@${checkout}|g" \
        -e "s|actions/github-script@v[0-9]\+|actions/github-script@${github_script}|g" \
        -e "s|actions/upload-artifact@v[0-9]\+|actions/upload-artifact@${upload_artifact}|g" \
        -e "s|actions/download-artifact@v[0-9]\+|actions/download-artifact@${download_artifact}|g" \
        -e "s|actions/cache@v[0-9]\+|actions/cache@${cache}|g" \
        "$file"
    
    if [[ "$(cat "$file")" != "$orig" ]]; then
        echo "  Updated: $file"
    fi
done

echo ""
echo "Done. Run 'git diff templates/' to see changes."
