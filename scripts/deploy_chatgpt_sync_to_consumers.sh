#!/bin/bash
# Deploy ChatGPT sync capability to consumer repos
# This script updates the agents-issue-intake.yml workflow in consumer repos
# to add chatgpt_sync mode alongside the existing agent_bridge mode

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE_FILE="${WORKFLOWS_ROOT}/templates/consumer-repo/.github/workflows/agents-issue-intake.yml"

# Consumer repos relative to Workflows parent directory
CONSUMER_REPOS=(
    "trip-planner"
    "Template"
    "Manager-Database"
    "Portable-Alpha-Extension-Model"
    "Travel-Plan-Permission"
    "Trend_Model_Project"
    "Collab-Admin"
)

echo "🚀 Deploying ChatGPT sync mode to consumer repos"
echo ""

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
    echo "❌ Template file not found: ${TEMPLATE_FILE}"
    exit 1
fi

for repo in "${CONSUMER_REPOS[@]}"; do
    REPO_PATH="$(cd "${WORKFLOWS_ROOT}/.." && pwd)/${repo}"
    TARGET_FILE="${REPO_PATH}/.github/workflows/agents-issue-intake.yml"

    echo "📦 Processing ${repo}..."

    if [[ ! -d "${REPO_PATH}" ]]; then
        echo "  ⚠️  Repo directory not found: ${REPO_PATH} (skipping)"
        continue
    fi

    if [[ ! -d "${REPO_PATH}/.github/workflows" ]]; then
        echo "  📁 Creating .github/workflows directory"
        mkdir -p "${REPO_PATH}/.github/workflows"
    fi

    # Backup existing file if present
    if [[ -f "${TARGET_FILE}" ]]; then
        cp "${TARGET_FILE}" "${TARGET_FILE}.backup"
        echo "  💾 Backed up existing workflow to ${TARGET_FILE}.backup"
    fi

    # Copy template
    cp "${TEMPLATE_FILE}" "${TARGET_FILE}"
    echo "  ✅ Deployed updated workflow"

    # Check if repo has git
    if [[ -d "${REPO_PATH}/.git" ]]; then
        cd "${REPO_PATH}"

        # Check if there are changes
        if git diff --quiet .github/workflows/agents-issue-intake.yml 2>/dev/null; then
            echo "  ℹ️  No changes detected (already up to date)"
        else
            echo "  📝 Changes detected - ready to commit"
            echo "     Run: cd ${REPO_PATH} && git add .github/workflows/agents-issue-intake.yml && git commit -m 'feat: add ChatGPT sync mode to issue intake'"
        fi
    fi

    echo ""
done

echo "✨ Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Review changes in each consumer repo"
echo "2. Commit and push updates"
echo "3. Test chatgpt_sync mode by running: Actions → Agents Issue Intake → Run workflow"
echo "   - Select 'chatgpt_sync' mode"
echo "   - Provide topic_files (e.g., 'topics.json' or 'agents/*.md')"
echo "   - Optionally enable 'apply_langchain_formatting'"
