#!/usr/bin/env bash
set -euo pipefail

MODEL_WAS_EXPLICIT=0
if (($# >= 1)); then
    MODEL_WAS_EXPLICIT=1
fi

MODEL="${1:-qwen3:4b}"
SPEECH_MODEL="${2:-small}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_PATH/bin/python"
OS_NAME="$(uname -s)"
OLLAMA_URL="http://127.0.0.1:11434"

step() {
    printf '\n==> %s\n' "$1"
}

fail() {
    echo "$1" >&2
    exit 1
}

python_is_supported() {
    local executable="${1:-}"
    [[ -n "$executable" ]] &&
        "$executable" -c \
            'import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
                >/dev/null 2>&1
}

activate_homebrew() {
    local candidate

    if command -v brew >/dev/null 2>&1; then
        BREW_BIN="$(command -v brew)"
    else
        for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
            if [[ -x "$candidate" ]]; then
                BREW_BIN="$candidate"
                break
            fi
        done
    fi

    if [[ -z "${BREW_BIN:-}" ]]; then
        return 1
    fi

    eval "$("$BREW_BIN" shellenv)"
}

install_macos_python() {
    if ! activate_homebrew; then
        step "Installing Homebrew"
        /bin/bash -c \
            "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        activate_homebrew || fail "Homebrew was installed but could not be added to PATH."
    fi

    step "Installing Python 3 and Tk support with Homebrew"
    "$BREW_BIN" install python python-tk
    eval "$("$BREW_BIN" shellenv)"
    hash -r
}

find_ollama() {
    local candidate

    if command -v ollama >/dev/null 2>&1; then
        command -v ollama
        return 0
    fi

    for candidate in \
        /usr/local/bin/ollama \
        /opt/homebrew/bin/ollama \
        /Applications/Ollama.app/Contents/Resources/ollama \
        "$HOME/Applications/Ollama.app/Contents/Resources/ollama"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    return 1
}

ollama_is_ready() {
    curl --silent --fail "$OLLAMA_URL/api/tags" >/dev/null 2>&1
}

wait_for_ollama() {
    local attempts="${1:-30}"
    local attempt

    for ((attempt = 0; attempt < attempts; attempt++)); do
        if ollama_is_ready; then
            return 0
        fi
        sleep 1
    done

    return 1
}

case "$OS_NAME" in
Darwin)
    MACOS_MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
    if [[ ! "$MACOS_MAJOR" =~ ^[0-9]+$ ]] || ((MACOS_MAJOR < 14)); then
        fail "Tubby's local Ollama workflow requires macOS 14 Sonoma or newer."
    fi
    ;;
Linux) ;;
*) fail "This setup script supports macOS and Linux only." ;;
esac

if [[ -z "${MODEL//[[:space:]]/}" ]]; then
    fail "The Ollama model name cannot be empty."
fi
if [[ -z "${SPEECH_MODEL//[[:space:]]/}" ]]; then
    fail "The speech model name cannot be empty."
fi

if ! command -v curl >/dev/null 2>&1; then
    fail "curl is required to install or connect to Ollama."
fi

step "Checking Python"
PYTHON_BIN="$(command -v python3 || true)"
if ! python_is_supported "$PYTHON_BIN"; then
    if [[ "$OS_NAME" == "Darwin" ]]; then
        install_macos_python
        PYTHON_BIN="$(command -v python3 || true)"
    else
        fail "Python 3.10 or newer is required."
    fi
fi

python_is_supported "$PYTHON_BIN" ||
    fail "Tubby requires Python 3.10 or newer with Tk support."

if [[ ! -x "$VENV_PYTHON" ]]; then
    step "Creating .venv"
    "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

step "Installing Tubby and Python dependencies"
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -e "$PROJECT_ROOT"

if [[ "${TUBBY_SKIP_SPEECH_MODEL_DOWNLOAD:-0}" != "1" ]]; then
    step "Downloading local speech model $SPEECH_MODEL"
    "$VENV_PYTHON" -c \
        'import sys; from tubby.media_transcript import download_transcription_model; download_transcription_model(sys.argv[1])' \
        "$SPEECH_MODEL"
fi

step "Checking Ollama"
OLLAMA_BIN="$(find_ollama || true)"
if [[ -z "$OLLAMA_BIN" ]]; then
    step "Installing Ollama"
    curl -fsSL https://ollama.com/install.sh | sh
    hash -r
    OLLAMA_BIN="$(find_ollama || true)"
fi

if [[ -z "$OLLAMA_BIN" ]]; then
    fail "Ollama installation finished, but the Ollama command could not be found."
fi

if ! ollama_is_ready; then
    step "Starting the local Ollama service"

    if [[ "$OS_NAME" == "Darwin" ]] && open -g -a Ollama >/dev/null 2>&1; then
        wait_for_ollama 20 || true
    fi

    if ! ollama_is_ready; then
        nohup "$OLLAMA_BIN" serve >"${TMPDIR:-/tmp}/tubby-ollama.log" 2>&1 &
        wait_for_ollama 30 || true
    fi
fi

if ! ollama_is_ready; then
    fail "Ollama did not start at $OLLAMA_URL. See ${TMPDIR:-/tmp}/tubby-ollama.log."
fi

step "Choosing an Ollama report model"
CHOOSER_ARGUMENTS=(
    -m
    tubby.ollama_models
    choose-setup
    --preferred
    "$MODEL"
)
if ((MODEL_WAS_EXPLICIT)); then
    CHOOSER_ARGUMENTS+=(--explicit)
fi
if [[ "${TUBBY_SKIP_MODEL_PULL:-0}" == "1" ]]; then
    CHOOSER_ARGUMENTS+=(--no-install)
fi

SELECTION_OUTPUT="$("$VENV_PYTHON" "${CHOOSER_ARGUMENTS[@]}")" ||
    fail "Could not choose an Ollama report model."
IFS=$'\t' read -r MODEL MODEL_STATE MODEL_LANGUAGE_SUPPORT <<<"$SELECTION_OUTPUT"
if [[ -z "$MODEL" || -z "$MODEL_STATE" ]]; then
    fail "Tubby returned an invalid Ollama model selection."
fi
if [[ "$MODEL_STATE" != "installed" && "$MODEL_STATE" != "missing" ]]; then
    fail "Tubby returned an unknown Ollama model state: $MODEL_STATE"
fi

if [[ "$MODEL_STATE" == "missing" ]]; then
    step "Downloading Ollama model $MODEL"
    "$OLLAMA_BIN" pull "$MODEL"
else
    step "Using installed Ollama model $MODEL"
fi

printf '\nTubby setup is complete.\n'
printf 'Report model: %s\n' "$MODEL"
printf 'Start the desktop app with:\n  ./.venv/bin/python -m tubby\n'
printf 'The downloader CLI remains available with:\n  ./.venv/bin/tubby --help\n'
