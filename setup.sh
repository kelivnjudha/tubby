#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-gemma4}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_PATH/bin/python"

step() {
    printf '\n==> %s\n' "$1"
}

step "Checking Python"
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10 or newer is required." >&2
    exit 1
fi
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
    echo "Tubby requires Python 3.10 or newer." >&2
    exit 1
}

if [[ ! -x "$VENV_PYTHON" ]]; then
    step "Creating .venv"
    python3 -m venv "$VENV_PATH"
fi

step "Installing Tubby and Python dependencies"
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -e "$PROJECT_ROOT"

step "Checking Ollama"
if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to install or connect to Ollama." >&2
    exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
    if [[ "$(uname -s)" == "Linux" ]]; then
        step "Installing Ollama"
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "Install Ollama from https://ollama.com/download and rerun setup.sh." >&2
        exit 1
    fi
fi

if ! curl --silent --fail http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    step "Starting the local Ollama service"
    nohup ollama serve >"${TMPDIR:-/tmp}/tubby-ollama.log" 2>&1 &
    for _ in $(seq 1 20); do
        sleep 1
        if curl --silent --fail http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            break
        fi
    done
fi

if ! curl --silent --fail http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama did not start at http://127.0.0.1:11434." >&2
    exit 1
fi

step "Downloading Ollama model $MODEL"
ollama pull "$MODEL"

printf '\nTubby setup is complete.\n'
printf 'Start the desktop app with:\n  ./.venv/bin/python -m tubby\n'
printf 'The downloader CLI remains available with:\n  ./.venv/bin/tubby --help\n'
