#!/bin/bash
#
# SPDX-License-Identifier: MIT
#
# trimui.portmaster.zip: PortMaster as a TrimUI app.
#
#   ./do_trimui_release.sh            from dist/PortMaster.zip (./do_release.sh first)
#   ./do_trimui_release.sh stable  from the latest stable PortMaster.zip on GitHub
#
# Writes dist/trimui.portmaster.zip.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${PM_DIST_DIR:-$REPO_DIR/dist}"

BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pm-trimui.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT
cd "$BUILD_DIR"

if [[ "${1:-}" == "stable" ]]; then
  curl -fL -o version.json "https://github.com/PortsMaster/PortMaster-GUI/releases/latest/download/version.json"
  curl -fL -o PortMaster.zip "$(jq -r '.stable.url' version.json)"
  PORTMASTER_ZIP="$BUILD_DIR/PortMaster.zip"
else
  PORTMASTER_ZIP="$DIST_DIR/PortMaster.zip"
fi

if [[ ! -f "$PORTMASTER_ZIP" ]]; then
  echo "Missing $PORTMASTER_ZIP, run ./do_release.sh first."
  exit 255
fi

mkdir -p Apps/PortMaster

(
  cd Apps/PortMaster
  unzip -q "$PORTMASTER_ZIP"

  cd PortMaster
  rm -f PortMaster.sh

  cp trimui/control.txt control.txt
  cp trimui/PortMaster.txt ../launch.sh
  cp trimui/config.json ../config.json
  cp trimui/icon.png ../icon.png

  rm -f tasksetter
  touch tasksetter
)

mkdir -p "$DIST_DIR"
rm -f "$DIST_DIR/trimui.portmaster.zip"
zip -9qr "$DIST_DIR/trimui.portmaster.zip" Apps/
echo "Built $DIST_DIR/trimui.portmaster.zip"
