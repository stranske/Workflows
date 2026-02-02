#!/bin/bash
echo "=== DUPLICATE APP_TOKEN ISSUES (Already fixed in 79d2b20) ==="
echo "1. agents-bot-comment-handler.yml - checking for duplicate app_token in cleanup job:"
grep -n "id: app_token" .github/workflows/agents-bot-comment-handler.yml | head -5

echo -e "\n2. selftest-reusable-ci.yml - checking for duplicate app_token:"
grep -n "id: app_token" .github/workflows/selftest-reusable-ci.yml | head -5

echo -e "\n3. maint-62-integration-consumer.yml - checking for duplicate app_token:"
grep -n "id: app_token" .github/workflows/maint-62-integration-consumer.yml | head -5

echo -e "\n=== MINTING ORDER ISSUES (Fixed in 210bb6e) ==="
echo "4. maint-coverage-guard.yml:"
echo "   First token use: $(grep -n 'token: \${{ steps.app_token' .github/workflows/maint-coverage-guard.yml | head -1)"
echo "   Mint step: $(grep -n 'Mint GitHub App Token' .github/workflows/maint-coverage-guard.yml | head -1)"

echo -e "\n5. maint-52-sync-dev-versions.yml:"
echo "   First token use: $(grep -n 'token: \${{ steps.app_token' .github/workflows/maint-52-sync-dev-versions.yml | head -1)"
echo "   Mint step: $(grep -n 'Mint GitHub App Token' .github/workflows/maint-52-sync-dev-versions.yml | head -1)"

echo -e "\n=== OTHER 'MISSING MINTING' COMMENTS (Need to verify if false positives) ==="
for f in agents-capability-check health-67-integration-sync-check health-codex-auth-check maint-50-tool-version-check maint-61-create-floating-v1-tag maint-69-sync-labels maint-auto-update-pypi-versions maint-sync-action-versions reusable-12-ci-docker; do
    echo "$f.yml:"
    first_use=$(grep -n 'token: \${{ steps.app_token' .github/workflows/$f.yml 2>/dev/null | head -1 | cut -d: -f1)
    mint_line=$(grep -n 'Mint GitHub App Token' .github/workflows/$f.yml 2>/dev/null | head -1 | cut -d: -f1)
    if [ -n "$first_use" ] && [ -n "$mint_line" ]; then
        if [ "$mint_line" -lt "$first_use" ]; then
            echo "   ✅ OK: Mint at line $mint_line, first use at line $first_use"
        else
            echo "   ❌ BUG: Mint at line $mint_line, first use at line $first_use"
        fi
    else
        echo "   ⚠️  Could not determine (mint: $mint_line, use: $first_use)"
    fi
done

echo -e "\n=== HARDCODED REF ISSUES (Enhancement suggestion, not a bug) ==="
echo "6. reusable-20-pr-meta.yml - 4 instances of 'ref: main'"
echo "   Before PR: $(git show 99643cb:.github/workflows/reusable-20-pr-meta.yml 2>/dev/null | grep -c 'ref: main')"
echo "   After PR:  $(grep -c 'ref: main' .github/workflows/reusable-20-pr-meta.yml)"
echo "   Status: Not changed by our PR - enhancement suggestion only"
