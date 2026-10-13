#!/bin/bash
#
# SPDX-License-Identifier: MIT
#
# muos.portmaster.zip: PortMaster laid out for muOS images.
#
#   ./do_muos_release.sh            from dist/PortMaster.zip (./do_release.sh first)
#   ./do_muos_release.sh stable  from the latest stable PortMaster.zip on GitHub
#
# Writes dist/muos.portmaster.zip.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${PM_DIST_DIR:-$REPO_DIR/dist}"

BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pm-muos.XXXXXX")"
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

mkdir -p mnt/mmc/MUOS/ roms/ports/PortMaster/

(
  cd mnt/mmc/MUOS/
  unzip -q "$PORTMASTER_ZIP"

  cd PortMaster
  cp muos/control.txt control.txt
  cp muos/control.txt "$BUILD_DIR/roms/ports/PortMaster/control.txt"
  cp muos/PortMaster.txt PortMaster.sh
  rm -f tasksetter
  touch tasksetter
)

mkdir -p "$DIST_DIR"
rm -f "$DIST_DIR/muos.portmaster.zip"
zip -9qr "$DIST_DIR/muos.portmaster.zip" roms/ mnt/
echo "Built $DIST_DIR/muos.portmaster.zip"
