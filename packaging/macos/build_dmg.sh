#!/usr/bin/env bash
set -euo pipefail

if (($# != 4)); then
    echo "Usage: $0 APP_PATH VERSION ARCHITECTURE OUTPUT_DIR" >&2
    exit 2
fi

APP_PATH="$1"
VERSION="$2"
ARCHITECTURE="$3"
OUTPUT_DIR="$4"

if [[ ! -d "$APP_PATH" ]]; then
    echo "App bundle not found: $APP_PATH" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tubby-dmg.XXXXXX")"
trap 'rm -rf "$STAGING_DIR"' EXIT

ditto "$APP_PATH" "$STAGING_DIR/Tubby.app"
ln -s /Applications "$STAGING_DIR/Applications"

DMG_PATH="$OUTPUT_DIR/Tubby-${VERSION}-macOS-${ARCHITECTURE}.dmg"
hdiutil create \
    -volname "Tubby ${VERSION}" \
    -srcfolder "$STAGING_DIR" \
    -format UDZO \
    -ov \
    "$DMG_PATH"
hdiutil verify "$DMG_PATH"

printf '%s\n' "$DMG_PATH"
