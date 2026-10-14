#!/usr/bin/env bash
# Overlay final pagination tests onto the prior collector in an isolated tree.
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
base_ref=${1:-fe0f9f35c197675a7bc4f2c836ce14e042590528}
proof_dir=$(mktemp -d /tmp/verifier-pagination-proof.XXXXXX)
trap 'rm -rf "$proof_dir"' EXIT
test_path=.github/scripts/__tests__/agents-verifier-context.test.js

mkdir -p "$proof_dir/.github/scripts/__tests__" "$proof_dir/templates/consumer-repo/.github/scripts"
cp "$repo_root/$test_path" "$proof_dir/$test_path"
ln -s "$repo_root/.github/scripts/__tests__/fixtures" "$proof_dir/.github/scripts/__tests__/fixtures"
for script_dir in .github/scripts templates/consumer-repo/.github/scripts; do
  git -C "$repo_root" show "$base_ref:$script_dir/agents_verifier_context.js" > "$proof_dir/$script_dir/agents_verifier_context.js"
  for helper in github-rate-limited-wrapper.js issue_scope_parser.js verifier_ci_query.js source_context.js; do
    ln -s "$repo_root/$script_dir/$helper" "$proof_dir/$script_dir/$helper"
  done
done

red_status=0
node --test --test-isolation=none --test-name-pattern='bounded listing' "$proof_dir/$test_path" > "$proof_dir/red.txt" 2>&1 || red_status=$?
sed 's/[[:blank:]]*$//' "$proof_dir/red.txt"
if [[ "$red_status" != 1 ]] || ! rg -q 'AssertionError' "$proof_dir/red.txt" || ! rg -q 'fail 2' "$proof_dir/red.txt"; then
  echo 'RED failed to execute both expected behavioral regressions.' >&2
  exit 1
fi

node --test --test-isolation=none --test-name-pattern='bounded listing|bounded recovery|explicit artifact scope|complete explicit exact-head' "$repo_root/$test_path"
echo 'PASS: prior collector RED; final source and template GREEN.'
