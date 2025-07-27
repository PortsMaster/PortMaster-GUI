#!/bin/bash

# Downloady of File
if [ ! -f "ports.json" ]; then
  curl -L -o ports.json $(curl -s https://api.github.com/repos/PortsMaster/PortMaster-New/releases/latest | jq -r '.assets[] | select(.name=="ports.json") | .browser_download_url')
fi

RUNTIME_ARCH="${RUNTIME_ARCH:-aarch64}"

# i still dont understand how this works
jq -r '
  .utils
  | to_entries
  | map(select(
      ( .key | ascii_downcase | contains("images") | not ) and
      ( .key | ascii_downcase | contains("gameinfo") | not ) and
      ( .value.runtime_arch == "'$RUNTIME_ARCH'" ) and
      ( .value.url != null )
    ))
  | .[]
  | "\(.value.url) \(.value.runtime_name) \(.value.md5)"
' "ports.json" | while read -r url key md5; do
  filename="$key"
  wget -O "$filename" "$url"
  if [ -n "$md5" ]; then
    downloaded_md5=$(md5sum "$filename" | awk '{print $1}')
    if [ "$downloaded_md5" != "$md5" ]; then
      echo "MD5 mismatch for $key! Expected $md5, got $downloaded_md5"
      rm -f "$filename"
    else
      echo "MD5 OK for $key"
    fi
  fi
done

rm -f ports.json
