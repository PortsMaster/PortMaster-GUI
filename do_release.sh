#!/bin/bash
#
# SPDX-License-Identifier: MIT
#
# Builds a PortMaster release into dist/, from a clean copy of the sources: the
# checkout itself is never changed.
#
#   ./do_release.sh [alpha|beta|stable] [version]
#       A release. The version defaults to now, as YYYY.MM.DD-HHMM (UTC), like the
#       release workflow. Makes dist/version.json from ./version.json (the release
#       workflow downloads the latest one there) or downloads it.
#
#   ./do_release.sh testsuite [version]
#       A test build plus dist/pmtest.zip, the "PortMaster Test Suite" port for testers
#       (tools/test_suite): it installs that build, runs every test and saves a report.
#
#   ./do_release.sh test [version]
#       A build for testing on devices. The version defaults to today's next unused
#       YYYY-MM-DD_XX69 (2026-10-13_0069, then _0169, ...): it never clashes with a
#       release, and shows it is a test build. No version.json, no installers.
#
# Writes dist/PortMaster.zip and dist/version, and for stable (or MAKE_INSTALL=Y)
# dist/Install.PortMaster.sh and the Full installers (unless NO_FULL_INSTALL=Y).
#
#   PM_DIST_DIR      where to put it all (default: ./dist)
#   PM_CACHE_DIR     downloads (makeself, runtimes), kept between builds (default: ./.cache/release)
#   PM_TEST_CHANNEL  the release channel a test build updates from (default: beta)
#   PM_VERSION_JSON  the version.json to update (default: ./version.json, else the latest release's)
#   PM_PMTEST_WHEELS a folder of pytest wheels for pmtest.zip (default: downloaded into PM_CACHE_DIR)
#   PM_PMTEST_UPLOAD a URL pmtest.zip sends its reports to (tools/test_suite/receive.py); none by default

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${PM_DIST_DIR:-$REPO_DIR/dist}"
CACHE_DIR="${PM_CACHE_DIR:-$REPO_DIR/.cache/release}"

MAKESELF_VERSION="2.5.0"
MAKESELF_SHA256="4d2fa9d898be22c63bb3c6bb7cc3dc97237700dea6d6ad898dcbec0289df0bc4"

usage() {
  sed -n '6,26p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

CHANNEL="${1:-alpha}"
VERSION="${2:-}"

case "$CHANNEL" in
  alpha|beta|stable|test|testsuite) ;;
  -h|--help|help) usage ;;
  *) echo "Unknown release channel: $CHANNEL"; usage ;;
esac

mkdir -p "$DIST_DIR"
TEST_BUILDS="$DIST_DIR/test-builds.txt"

## Today's next unused test version: YYYY-MM-DD_0069, _0169, ... _9969.
next_test_version() {
  local today number candidate
  today="$(date +%Y-%m-%d)"

  for number in $(seq 0 99); do
    candidate="$(printf '%s_%02d69' "$today" "$number")"
    if ! grep -qx "$candidate" "$TEST_BUILDS" 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done

  echo "Out of test versions for $today." >&2
  return 1
}

if [ -z "$VERSION" ]; then
  if [ "$CHANNEL" = "test" ] || [ "$CHANNEL" = "testsuite" ]; then
    VERSION="$(next_test_version)"
  else
    VERSION="$(date -u +%Y.%m.%d-%H%M)"
  fi
fi

if [ "${PM_PRINT_VERSION:-}" = "Y" ]; then
  echo "$VERSION"
  exit 0
fi

IS_TEST=""
case "$CHANNEL" in
  test|testsuite) IS_TEST="Y" ;;
esac

STAMP_CHANNEL="$CHANNEL"
if [ -n "$IS_TEST" ]; then
  STAMP_CHANNEL="${PM_TEST_CHANNEL:-beta}"
fi

for tool in zip python3; do
  if ! command -v "$tool" > /dev/null; then
    echo "do_release.sh needs $tool."
    exit 1
  fi
done

echo "Building PortMaster $VERSION ($CHANNEL)"

BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pm-release.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT

## -- A clean copy of the sources -------------------------------------------------
## From a checkout: what git knows about (tracked files as they are on disk, and new
## files that aren't ignored). Logs, config/, __pycache__,
## ports installed while testing, ... never get in. Without git (the release
## workflow deletes .git): the tree as it is.
cd "$REPO_DIR"
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  {
    git ls-files -z --cached --others --exclude-standard -- PortMaster tools tests pytest.ini
  } | while IFS= read -r -d '' file_name; do
    ## (tracked files deleted on disk are still listed)
    [ -f "$file_name" ] && printf '%s\0' "$file_name"
  done | tar -cf - --null -T - | tar -xf - -C "$BUILD_DIR"
else
  tar -cf - --exclude='__pycache__' --exclude='.DS_Store' --exclude='._*' PortMaster tools tests pytest.ini | tar -xf - -C "$BUILD_DIR"
fi

cd "$BUILD_DIR"

## -- Version -----------------------------------------------------------------------
python3 tools/pm_release.py "$STAMP_CHANNEL" "$VERSION"
echo "$VERSION" > PortMaster/version

## -- The zips ----------------------------------------------------------------------
echo "Creating pylibs.zip"
(
  cd PortMaster
  zip -9qr pylibs.zip exlibs/ pylibs/ \
      -x '*__pycache__*' \
      -x '*.DS_Store' \
      -x '._*' \
      -x '*NotoSans*.ttf'
)

echo "Creating PortMaster.zip"
zip -9qr PortMaster.zip PortMaster/ \
    -x 'PortMaster/pylibs/*' \
    -x 'PortMaster/exlibs/*' \
    -x 'PortMaster/config/*' \
    -x 'PortMaster/themes/*' \
    -x 'PortMaster/libs/*.squashfs' \
    -x 'PortMaster/libs/*.squashfs.md5' \
    -x 'PortMaster/pugwash.bak' \
    -x 'PortMaster/log.txt' \
    -x 'PortMaster/pugwash.txt' \
    -x 'PortMaster/harbourmaster.txt' \
    -x 'PortMaster/*_flag' \
    -x '*__pycache__*' \
    -x '*.DS_Store' \
    -x '*/._*'

## -- Installers --------------------------------------------------------------------
if [ "$CHANNEL" = "stable" ] || [ "${MAKE_INSTALL:-}" = "Y" ]; then
  echo "Creating Installers"
  mkdir -p "$CACHE_DIR"

  MAKESELF_RUN="$CACHE_DIR/makeself-$MAKESELF_VERSION.run"
  MAKESELF="$CACHE_DIR/makeself-$MAKESELF_VERSION/makeself.sh"

  if [ ! -f "$MAKESELF" ]; then
    if [ ! -f "$MAKESELF_RUN" ]; then
      curl -fL -o "$MAKESELF_RUN" "https://github.com/megastep/makeself/releases/download/release-$MAKESELF_VERSION/makeself-$MAKESELF_VERSION.run"
    fi

    echo "$MAKESELF_SHA256  $MAKESELF_RUN" | sha256sum -c -
    (cd "$CACHE_DIR" && sh "$MAKESELF_RUN" --target "makeself-$MAKESELF_VERSION" > /dev/null)
  fi

  mkdir -p pm_release
  cp PortMaster.zip tools/installer.sh pm_release/

  "$MAKESELF" --header tools/makeself-header.sh pm_release "Install.PortMaster.sh" "PortMaster Installer" ./installer.sh

  if [ -z "${NO_FULL_INSTALL:-}" ]; then
    for arch in aarch64 x86_64; do
      if [ ! -f "$CACHE_DIR/runtimes.$arch.zip" ]; then
        echo "Downloading Runtimes for $arch."
        (cd "$CACHE_DIR" && RUNTIME_ARCH="$arch" "$BUILD_DIR/tools/download_runtimes.sh")
      fi

      if [ "$arch" = "aarch64" ]; then
        SCRIPT_NAME=""
      else
        SCRIPT_NAME=".$arch"
      fi

      cp "$CACHE_DIR/runtimes.$arch.zip" pm_release/runtimes.zip
      "$MAKESELF" --header tools/makeself-header.sh pm_release "Install.Full${SCRIPT_NAME}.PortMaster.sh" "PortMaster Full Installer" ./installer.sh
    done
  fi

  rm -f "$DIST_DIR"/Install*PortMaster.sh
  cp Install*PortMaster.sh "$DIST_DIR/"
fi

## -- The PortMaster Test Suite port -------------------------------------------------
if [ "$CHANNEL" = "testsuite" ]; then
  echo "Creating pmtest.zip"

  ## pytest and what it needs, pure python, the newest that still run on Python 3.7.
  PMTEST_WHEELS="${PM_PMTEST_WHEELS:-$CACHE_DIR/pmtest-wheels}"
  if [ -z "${PM_PMTEST_WHEELS:-}" ] && [ ! -f "$PMTEST_WHEELS/.complete" ]; then
    mkdir -p "$PMTEST_WHEELS"
    ${PM_PIP:-python3 -m pip} download --quiet --no-deps --only-binary=:all: \
        --python-version 3.7 --implementation py --abi none --platform any -d "$PMTEST_WHEELS" \
        pytest==7.4.4 pluggy==1.2.0 iniconfig==2.0.0 packaging==23.2 exceptiongroup==1.2.2 \
        tomli==2.0.1 importlib_metadata==6.7.0 zipp==3.15.0 typing_extensions==4.7.1
    touch "$PMTEST_WHEELS/.complete"
  fi

  PMTEST="pmtest_build/pmtest"
  mkdir -p "$PMTEST/site" "$PMTEST/tree" "$PMTEST/reports"
  cp "tools/test_suite/PortMaster Test Suite.sh" pmtest_build/
  cp tools/test_suite/pmtest/*.py tools/test_suite/pmtest/port.json "$PMTEST/"
  cp PortMaster.zip "$PMTEST/"
  touch "$PMTEST/reports/.keep"
  if [ -n "${PM_PMTEST_UPLOAD:-}" ]; then
    echo "$PM_PMTEST_UPLOAD" > "$PMTEST/upload.txt"
  fi

  for wheel in "$PMTEST_WHEELS"/*.whl; do
    python3 -m zipfile -e "$wheel" "$PMTEST/site/"
  done

  ## The code under test, as stamped above, without what the tests never touch.
  tar -cf - \
      --exclude='PortMaster/runtimes' --exclude='PortMaster/libs' --exclude='PortMaster/utils/patcher' \
      --exclude='PortMaster/7zzs.*' --exclude='PortMaster/innoextract.*' --exclude='PortMaster/astcenc.*' \
      --exclude='PortMaster/xdelta3*' --exclude='PortMaster/gptokeyb*' --exclude='PortMaster/sdl2imgshow*' \
      --exclude='PortMaster/portmsg.*' --exclude='PortMaster/*.so' --exclude='PortMaster/pylibs.zip' \
      --exclude='NotoSans.tar.xz' --exclude='__pycache__' \
      PortMaster tests tools pytest.ini | tar -xf - -C "$PMTEST/tree"

  (cd pmtest_build && zip -9qr ../pmtest.zip "PortMaster Test Suite.sh" pmtest)
  cp pmtest.zip "$DIST_DIR/"
  ## harbourmaster checks it when installing <url>/pmtest.zip.md5
  (cd "$DIST_DIR" && md5sum pmtest.zip > pmtest.zip.md5)
fi

## -- version.json: what each channel's PortMaster updates to -----------------------
if [ -n "$IS_TEST" ]; then
  echo "$VERSION" > version

else
  VERSION_JSON="${PM_VERSION_JSON:-$REPO_DIR/version.json}"
  if [ -f "$VERSION_JSON" ]; then
    cp "$VERSION_JSON" version.json
  else
    curl -fL -o version.json "https://github.com/PortsMaster/PortMaster-GUI/releases/latest/download/version.json"
  fi

  python3 tools/pm_version.py "$CHANNEL" "$VERSION"
  cp version.json "$DIST_DIR/version.json"
fi

cp PortMaster.zip version "$DIST_DIR/"

if [ -n "$IS_TEST" ]; then
  echo "$VERSION" >> "$TEST_BUILDS"
fi

echo "Built PortMaster $VERSION ($CHANNEL) in $DIST_DIR"
