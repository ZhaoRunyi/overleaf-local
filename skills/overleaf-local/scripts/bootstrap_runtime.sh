#!/usr/bin/env bash
set -euo pipefail

codex_home="${CODEX_HOME:-$HOME/.codex}"
runtime="${OVERLEAF_LOCAL_RUNTIME:-$codex_home/skill-runtimes/overleaf-local}"
if command -v uv >/dev/null 2>&1; then
    export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$codex_home/uv/python}"
    export UV_CACHE_DIR="${UV_CACHE_DIR:-$codex_home/uv/cache}"
    export UV_TOOL_DIR="${UV_TOOL_DIR:-$codex_home/uv/tools}"
    uv venv --python python3 "$runtime"
    uv pip install --python "$runtime/bin/python" pillow
else
    python3 -m venv "$runtime"
    "$runtime/bin/python" -m pip install --upgrade pip pillow
fi
printf 'Overleaf Local runtime ready: %s\n' "$runtime/bin/python"
