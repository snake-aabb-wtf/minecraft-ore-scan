#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "[INFO] Virtual environment not found. Creating it..."
    if ! command -v python3 >/dev/null 2>&1; then
        echo "[ERROR] python3 was not found in PATH."
        exit 1
    fi

    if ! python3 -m venv "$VENV_DIR"; then
        echo "[ERROR] Failed to create the virtual environment."
        exit 1
    fi
else
    echo "[INFO] Virtual environment found."
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "[ERROR] Virtual environment Python executable is missing."
    exit 1
fi

echo "[INFO] Checking dependencies..."
if ! "$VENV_PYTHON" -c "import nbtlib, openpyxl" >/dev/null 2>&1; then
    echo "[INFO] Installing dependencies..."
    if ! "$VENV_PYTHON" -m pip install -r requirements.txt; then
        echo "[ERROR] Failed to install dependencies."
        exit 1
    fi
else
    echo "[INFO] Dependencies are already installed."
fi

echo "[INFO] Starting application..."
exec "$VENV_PYTHON" main.py
