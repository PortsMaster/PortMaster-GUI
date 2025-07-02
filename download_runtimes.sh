#!/bin/bash

# Downloady of Fily
if [ ! -f "ports.json" ]; then
  curl -L -o ports.json $(curl -s https://api.github.com/repos/PortsMaster/PortMaster-New/releases/latest | jq -r '.assets[] | select(.name=="ports.json") | .browser_download_url')
fi

mkdir -p runtimes

# i still dont understand how this works
jq -r '
  .utils
  | to_entries
  | map(select(
      ( .key | ascii_downcase | contains("images") | not ) and
      ( .key | ascii_downcase | contains("gameinfo") | not ) and
      ( .value.runtime_arch == "aarch64" ) and
      ( .value.url != null )
    ))
  | .[].value.url
' "ports.json" | while read -r url; do
  wget -P runtimes "$url"
done
