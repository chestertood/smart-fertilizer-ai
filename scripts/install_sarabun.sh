#!/usr/bin/env bash
# Install the bundled Sarabun font (Thai + Latin) for the current user on
# Ubuntu/Debian. No sudo, no network: copies assets/fonts/Sarabun-*.ttf into
# ~/.local/share/fonts and refreshes the font cache.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../assets/fonts" && pwd)"
DEST="$HOME/.local/share/fonts/sarabun"

mkdir -p "$DEST"
cp "$SRC"/Sarabun-*.ttf "$DEST"/
fc-cache -f "$DEST"

fc-list :family=Sarabun | head -n 3
echo "Sarabun installed to $DEST"
