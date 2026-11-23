# shellcheck shell=bash
# Shared tool lookup and version checks for the local validation entry points.

ensure_package_version() {
    local package_name="$1"
    local pinned_version="$2"
    local module_name="${3:-$1}"

    if [[ -z "$pinned_version" ]]; then
        return 0
    fi

    local current_version
    current_version=$(python - <<PY 2>/dev/null
try:
    import ${module_name} as _pkg  # type: ignore[import]
    print(getattr(_pkg, "__version__", ""))
except Exception:
    print("")
PY
)

    if [[ "$current_version" != "$pinned_version" ]]; then
        echo -e "${YELLOW}Installing ${package_name}==${pinned_version} to match CI${NC}"
        python -m pip install --disable-pip-version-check --quiet "${package_name}==${pinned_version}"
    fi
}

ensure_actionlint() {
    if command -v actionlint >/dev/null 2>&1; then
        ACTIONLINT_BIN=$(command -v actionlint)
        return 0
    fi

    local cache_dir=".cache/tools"
    mkdir -p "$cache_dir"
    if [[ -x "$cache_dir/actionlint" ]]; then
        ACTIONLINT_BIN="$cache_dir/actionlint"
        return 0
    fi

    echo -e "${YELLOW}Downloading actionlint for workflow validation...${NC}"
    local downloader="$cache_dir/download-actionlint.bash"
    if ! curl -sSfL "https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash" -o "$downloader"; then
        echo -e "${YELLOW}⚠ Unable to fetch actionlint downloader; skipping workflow linting${NC}"
        return 1
    fi

    if bash "$downloader" "$1" "$cache_dir" >/tmp/actionlint-download.log 2>&1 && [[ -x "$cache_dir/actionlint" ]]; then
        ACTIONLINT_BIN="$cache_dir/actionlint"
        return 0
    fi

    echo -e "${YELLOW}⚠ Failed to download actionlint; skipping workflow linting${NC}"
    return 1
}
