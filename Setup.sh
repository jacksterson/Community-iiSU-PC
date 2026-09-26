#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 was not found. Please install Python 3.11+."
    exit 1
fi

if ! command -v java >/dev/null 2>&1 || ! command -v keytool >/dev/null 2>&1; then
    echo "Java and keytool are required for APK patching and signing."
    echo "Please install a JDK (e.g. sudo pacman -S jdk-openjdk)."
    exit 1
fi

exec python3 -m bridge.ui.setup_app "$@"
