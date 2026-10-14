#!/usr/bin/env python3
#
# SPDX-License-Identifier: MIT
#
# Collects PortMaster Test Suite reports over the LAN. Build the suite with
#
#   PM_PMTEST_UPLOAD=http://<this machine>:8770/ ./do_release.sh testsuite
#
# and run this; each finished run POSTs its report zip here:
#
#   python3 -I tools/test_suite/receive.py <folder> [--port 8770]
#
# Reports are untrusted: only a zip with a summary.json is kept, under a cleaned-up
# name, never overwriting one already there. Standard library only, Python 3.7+.

import argparse
import datetime
import http.server
import io
import json
import re
import sys
import zipfile
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024


def clean_name(name):
    """A safe file name ending in .zip, from the X-Report-Name header."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name or "").name).strip("._")[:120]
    if not name:
        name = "report-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    if not name.endswith(".zip"):
        name += ".zip"

    return name


def check_report(data):
    """The report's summary.json as a dict, or raises ValueError."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            info = zf.getinfo("summary.json")
            if info.file_size > 1024 * 1024:
                raise ValueError("summary.json too big")

            return json.loads(zf.read(info).decode("utf-8"))

    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ValueError(f"not a report: {err}")


def save_report(folder, name, data):
    """Saves it as folder/name, or name-1.zip etc. if that's taken. The path."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    base = clean_name(name)[:-4]
    path = folder / (base + ".zip")
    count = 1
    while path.exists():
        path = folder / f"{base}-{count}.zip"
        count += 1

    path.write_bytes(data)
    return path


def make_handler(folder, log=print):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1

            if not 0 < length <= MAX_BYTES:
                return self.answer(413 if length > MAX_BYTES else 411, "bad length")

            data = self.rfile.read(length)
            try:
                summary = check_report(data)
            except ValueError as err:
                return self.answer(400, str(err))

            path = save_report(folder, self.headers.get("X-Report-Name"), data)
            info = summary.get("info", {}) if isinstance(summary, dict) else {}
            statuses = " ".join(
                f"{section.get('key')}={section.get('status')}"
                for section in summary.get("sections", []) if isinstance(section, dict))
            log(f"{self.client_address[0]}: {path.name} | {info.get('cfw', '?')} {info.get('cfw_version', '')} "
                f"on {info.get('device', '?')} | {statuses}")
            self.answer(200, "saved")

        def answer(self, code, text):
            body = (text + "\n").encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collects PortMaster Test Suite reports.")
    parser.add_argument("folder")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--bind", default="")
    options = parser.parse_args(argv)

    server = http.server.ThreadingHTTPServer((options.bind, options.port), make_handler(options.folder, log=lambda text: print(text, flush=True)))
    print(f"Saving reports to {options.folder}, listening on port {options.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == '__main__':
    sys.exit(main())
