#!/bin/bash

# Downloady of File
if [ ! -f "runtimes_zips.json" ]; then
  curl -L -o runtimes_zips.json $(curl -s https://api.github.com/repos/PortsMaster/PortMaster-New/releases/latest | jq -r '.assets[] | select(.name=="runtimes_zips.json") | .browser_download_url')
fi

RUNTIME_ARCH="${RUNTIME_ARCH:-aarch64}"

OUT="runtimes.$RUNTIME_ARCH.zip"

# Exit early if already present and valid
if [ -f "$OUT" ]; then
    echo "$OUT already exists, skipping download"
    exit 0
fi

# Pick popular first, fall back to all
ENTRY="$(jq -r --arg arch "$RUNTIME_ARCH" '
    ( .[] | select(.file_name == ("runtimes.popular." + $arch + ".zip")) ),
    ( .[] | select(.file_name == ("runtimes.all." + $arch + ".zip")) )
    | . | @base64
    ' "runtimes_zips.json" | head -n 1)"

if [ -z "$ENTRY" ]; then
    echo "No runtime zip found for architecture: $RUNTIME_ARCH" >&2
    exit 1
fi

# Decode selected entry
decode() {
    echo "$1" | base64 -d | jq -r "$2"
}

URL="$(decode "$ENTRY" '.url')"
MD5_EXPECTED="$(decode "$ENTRY" '.md5')"

echo "Downloading $URL"
TMP="$OUT.tmp"

if command -v curl >/dev/null 2>&1; then
    curl -L -f -o "$TMP" "$URL" || exit 1
elif command -v wget >/dev/null 2>&1; then
    wget -O "$TMP" "$URL" || exit 1
else
    echo "Neither curl nor wget is available" >&2
    exit 1
fi

# Verify checksum
MD5_ACTUAL="$(md5sum "$TMP" | awk '{print $1}')"

if [ "$MD5_ACTUAL" != "$MD5_EXPECTED" ]; then
    echo "MD5 mismatch!" >&2
    echo "Expected: $MD5_EXPECTED" >&2
    echo "Actual:   $MD5_ACTUAL" >&2
    rm -f "$TMP"
    exit 1
fi

mv "$TMP" "$OUT"
echo "Downloaded and verified: $OUT"
