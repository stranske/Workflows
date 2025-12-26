#!/bin/bash
# Setup a local Python virtual environment and install dependencies.

# Minimum Node.js major version required for workflow helper tests
REQUIRED_NODE_MAJOR=20

require_node() {
	if ! command -v node >/dev/null 2>&1; then
		echo "::error::Node.js v${REQUIRED_NODE_MAJOR}+ is required for workflow helper tests. Install Node.js and re-run setup." >&2
		return 1
	fi

	local raw_version major
	raw_version=$(node --version 2>/dev/null | sed 's/^v//')
	major=${raw_version%%.*}

	if [[ -z "$major" ]]; then
		echo "::error::Unable to determine Node.js version from '${raw_version}'." >&2
		return 1
	fi

	if (( major < REQUIRED_NODE_MAJOR )); then
		echo "::error::Node.js v${REQUIRED_NODE_MAJOR}+ is required; found v${raw_version}." >&2
		return 1
	fi

	return 0
}

# Detect if this script is being sourced (so we don't leak set -euo into the parent shell)
# shellcheck disable=SC2039
if (return 0 2>/dev/null); then
	# Sourced: run the install in a child shell to keep strict modes local,
	# then activate the venv in the current shell.
	if ! require_node; then
		return 1
	fi
	(
		set -euo pipefail
		ENV_DIR=".venv"
		python3 -m venv "$ENV_DIR"
		# shellcheck source=/dev/null
		source "$ENV_DIR/bin/activate"
                pip install --upgrade pip
				pip install uv
				uv pip sync requirements.lock
                pip install --no-deps -e ".[dev]"

                # Install pre-commit hooks (including pre-push for sync check)
		if ! pre-commit install --install-hooks --hook-type pre-commit --hook-type pre-push; then
			echo "::warning::pre-commit install failed, but continuing. Git hooks may not be available."
		fi

		# Ensure CLI wrapper script is executable
                if ! chmod +x scripts/trend; then
                        echo "::warning::chmod +x scripts/trend failed, but continuing. CLI wrapper may not be executable."
                fi
                if ! chmod +x scripts/trend-model; then
                        echo "::warning::chmod +x scripts/trend-model failed, but continuing. CLI wrapper may not be executable."
                fi
	)
	# Now activate in the current shell so the user can keep working
	# shellcheck disable=SC1091
	. ".venv/bin/activate"
	echo "Environment ready and activated."
        echo "CLI available as: 'trend' (if installed) or './scripts/trend' (legacy: './scripts/trend-model')"
        return 0 2>/dev/null || exit 0
fi

# Executed normally (recommended): strict mode is safe here
set -euo pipefail

if ! require_node; then
	exit 1
fi

ENV_DIR=".venv"

python3 -m venv "$ENV_DIR"
# shellcheck source=/dev/null
source "$ENV_DIR/bin/activate"

pip install --upgrade pip
pip install uv
uv pip sync requirements.lock
pip install --no-deps -e ".[dev]"

# Install pre-commit hooks (including pre-push for sync check)
if ! pre-commit install --install-hooks --hook-type pre-commit --hook-type pre-push; then
	echo "::warning::pre-commit install failed, but continuing. Git hooks may not be available."
fi

# Ensure CLI wrapper script is executable
if ! chmod +x scripts/trend; then
        echo "::warning::chmod +x scripts/trend failed, but continuing. CLI wrapper may not be executable."
fi
if ! chmod +x scripts/trend-model; then
        echo "::warning::chmod +x scripts/trend-model failed, but continuing. CLI wrapper may not be executable."
fi

echo "Environment setup complete. Activate later with 'source $ENV_DIR/bin/activate'."
echo "CLI available as: 'trend' (if installed) or './scripts/trend' (legacy: './scripts/trend-model')"
