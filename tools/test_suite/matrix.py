#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# The coverage matrix for PortMaster Test Suite reports: which CFW / version / device
# combinations ran, how each section went, and which tests failed where.
#
#   python3 -I tools/test_suite/matrix.py <folder of report zips> [--out DIR] [--title TEXT]
#
# Writes DIR/matrix.json and DIR/matrix.html (self-contained, no scripts). Reports come
# from testers, so they are only read: summary.json out of each zip, size-capped, nothing
# extracted or run.

import argparse
import datetime
import html
import json
import re
import sys
import zipfile
from pathlib import Path


MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_SUMMARY_BYTES = 1024 * 1024
MAX_ENVIRONMENT_BYTES = 256 * 1024

## The suite's sections, in its order, with short column names.
SECTIONS = (
    ("install", "Install"),
    ("pytest", "Tests"),
    ("gui", "GUI"),
    ("smoke", "Online"),
    ("interactive", "Buttons"),
    )

INFO_KEYS = ("cfw", "cfw_version", "os", "device", "arch", "python", "sdl", "portmaster", "started")


################################################################################
## Reading reports
def _text(value, limit=300):
    return str(value if value is not None else "")[:limit]


def _failures(details):
    """[(test id, message)] from a section's details ("Failed:" then "- id: message" lines)."""
    failures = []
    in_failed = False
    for line in details.splitlines():
        if line.strip() == "Failed:":
            in_failed = True
            continue

        if not line.startswith("- "):
            in_failed = False
            continue

        if in_failed:
            test_id, _, message = line[2:].partition(": ")
            failures.append((test_id.strip(), message.strip()))

    return failures


def _gui_how(summary):
    match = re.search(r"\((on the real screen|headless[^)]*\)?)\)\s*$", summary)
    if match is None:
        return ""

    return "real screen" if match.group(1) == "on the real screen" else "headless"


def _environment(zf):
    """KEY=value pairs from the report's device/environment.txt, {} without one."""
    try:
        member = zf.getinfo("device/environment.txt")
        if member.file_size > MAX_ENVIRONMENT_BYTES:
            return {}

        text = zf.read(member).decode("utf-8", "replace")

    except KeyError:
        return {}

    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def read_report(zip_path):
    """One matrix row from a report zip, or None if it isn't a usable report."""
    zip_path = Path(zip_path)
    try:
        if zip_path.stat().st_size > MAX_ZIP_BYTES:
            return None

        with zipfile.ZipFile(str(zip_path)) as zf:
            member = zf.getinfo("summary.json")
            if member.file_size > MAX_SUMMARY_BYTES:
                return None

            data = json.loads(zf.read(member).decode("utf-8"))
            environment = _environment(zf)

    except (OSError, KeyError, ValueError, zipfile.BadZipFile, UnicodeDecodeError):
        return None

    if not isinstance(data, dict) or not isinstance(data.get('info'), dict) or not isinstance(data.get('sections'), list):
        return None

    info = data['info']
    row = {key: _text(info.get(key)) for key in INFO_KEYS}
    row['video_drivers'] = [_text(driver, 40) for driver in info.get('video_drivers', []) if isinstance(driver, str)][:20]
    ## Telling devices apart: DEVICE_NAME is just the SoC on some (sun50iw10: TrimUI Brick
    ## and MagicX Zero28). Reports from before the suite recorded these: environment.txt.
    row['platform'] = _text(info.get('platform') or environment.get("PLATFORM"), 60)
    row['model'] = _text(info.get('model'), 80)
    width, height = environment.get("DISPLAY_WIDTH"), environment.get("DISPLAY_HEIGHT")
    row['display'] = _text(info.get('display') or (f"{width}x{height}" if width and height else ""), 20)
    row['ram_mb'] = _text(info.get('ram_mb') or environment.get("DEVICE_RAM_MB"), 10)
    row['report'] = zip_path.name
    row['scrubbed'] = data.get('scrubbed') is True
    row['sections'] = {}
    row['failures'] = []

    for section in data['sections']:
        if not isinstance(section, dict):
            continue

        key = _text(section.get('key'), 40)
        summary = _text(section.get('summary'))
        details = _text(section.get('details'), 20000)
        row['sections'][key] = {
            'status': _text(section.get('status'), 10),
            'summary': summary,
            'details': details,
            }

        if section.get('status') == "fail":
            failures = _failures(details) or [("", summary)]
            row['failures'].extend({'section': key, 'test': test, 'message': message[:300]} for test, message in failures)

    row['gui_how'] = _gui_how(row['sections'].get('gui', {}).get('summary', ""))
    row['ok'] = not any(section['status'] == "fail" for section in row['sections'].values())
    return row


def read_reports(folder):
    rows = []
    for zip_path in sorted(Path(folder).rglob("*.zip")):
        row = read_report(zip_path)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda row: row['started'], reverse=True)
    return rows


def device_key(row):
    """The device as the matrix tells them apart: name, spruce's platform, display and RAM."""
    return " ".join(part for part in (row['device'], row['platform'], row['display'], row['ram_mb']) if part)


def group_rows(rows):
    """{(cfw, cfw_version, device key): [rows, newest first]}, sorted by CFW then device."""
    groups = {}
    for row in rows:
        groups.setdefault((row['cfw'], row['cfw_version'], device_key(row)), []).append(row)

    return dict(sorted(groups.items(), key=lambda item: tuple(part.lower() for part in item[0])))


def failure_index(rows):
    """[(test id, message, [rows])], the tests failing on the most devices first."""
    index = {}
    for row in rows:
        for failure in row['failures']:
            key = failure['test'] or f"{failure['section']}: {failure['message']}"
            entry = index.setdefault(key, [failure['message'], []])
            if row not in entry[1]:
                entry[1].append(row)

    return sorted(((test, message, found) for test, (message, found) in index.items()), key=lambda item: (-len(item[2]), item[0]))


################################################################################
## The page
STATUS_LABEL = {"pass": "Pass", "fail": "Fail", "skip": "Skip", "info": "Info"}

CSS = """
/* Layout: one column, summary line, coverage table grouped by CFW, failures, then every run. */
:root {
  --bg: #f6f7f9; --surface: #ffffff; --fg: #1b2230; --muted: #5b6577; --line: #dde1e8;
  --accent: #2f5bd3;
  --pass: #1f7a4d; --pass-bg: #e3f3ea; --fail: #b3261e; --fail-bg: #fbe5e3; --skip: #6b6f7a; --skip-bg: #eceef2;
  --font-display: "Chakra Petch", "Segoe UI", system-ui, sans-serif;
  --font-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --font-data: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12161d; --surface: #1a2029; --fg: #e4e8ef; --muted: #9aa4b5; --line: #2c3442;
  --accent: #7d9cf0;
  --pass: #6fd29d; --pass-bg: #173326; --fail: #ff8a80; --fail-bg: #3a1c1a; --skip: #a3a9b5; --skip-bg: #252b35;
  color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #12161d; --surface: #1a2029; --fg: #e4e8ef; --muted: #9aa4b5; --line: #2c3442;
  --accent: #7d9cf0;
  --pass: #6fd29d; --pass-bg: #173326; --fail: #ff8a80; --fail-bg: #3a1c1a; --skip: #a3a9b5; --skip-bg: #252b35;
  color-scheme: dark; }
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); line-height: 1.5; }
.page { max-width: 1180px; margin: 0 auto; padding-inline: 16px; padding-block: 32px 64px; display: grid; gap: 40px; }
h1, h2 { font-family: var(--font-display); font-weight: 600; text-wrap: balance; margin: 0; }
h1 { font-size: 2rem; letter-spacing: 0.01em; }
h2 { font-size: 1.25rem; }
header { display: grid; gap: 8px; }
.lede { color: var(--muted); margin: 0; max-width: 70ch; }
.counts { display: flex; flex-wrap: wrap; gap: 8px 28px; margin: 8px 0 0; padding: 0; list-style: none; }
.counts li { display: grid; }
.counts b { font-family: var(--font-display); font-size: 1.6rem; font-variant-numeric: tabular-nums; line-height: 1.2; }
.counts span { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; }
section { display: grid; gap: 12px; min-width: 0; }
.scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 0.875rem; }
th, td { padding: 8px 10px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); }
thead th { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; white-space: nowrap; }
tbody tr:last-child td { border-bottom: 0; }
tr.cfw th { background: var(--bg); font-family: var(--font-display); font-size: 0.95rem; color: var(--accent); }
.data { font-family: var(--font-data); font-size: 0.8rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
.muted { color: var(--muted); }
.chip { display: inline-block; min-width: 3.4em; text-align: center; padding: 1px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
.chip.pass { color: var(--pass); background: var(--pass-bg); }
.chip.fail { color: var(--fail); background: var(--fail-bg); }
.chip.skip, .chip.info, .chip.none { color: var(--skip); background: var(--skip-bg); }
.failures { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.failures li { background: var(--surface); border: 1px solid var(--line); border-left: 3px solid var(--fail); border-radius: 6px; padding: 10px 14px; display: grid; gap: 4px; min-width: 0; }
.failures code { font-family: var(--font-data); font-size: 0.8rem; overflow-wrap: anywhere; }
.failures .where { color: var(--muted); font-size: 0.85rem; }
.empty { color: var(--muted); margin: 0; }
details { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 8px 14px; }
details + details { margin-top: 8px; }
summary { cursor: pointer; display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; }
summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
details pre { font-family: var(--font-data); font-size: 0.78rem; white-space: pre-wrap; overflow-wrap: anywhere; margin: 8px 0 0; color: var(--muted); }
details h3 { font-size: 0.9rem; margin: 12px 0 0; }
footer { color: var(--muted); font-size: 0.8rem; }
"""


def _chip(status, text=None):
    status = status if status in STATUS_LABEL else "none"
    return f'<span class="chip {status}">{html.escape(text or STATUS_LABEL.get(status, "—"))}</span>'


def _e(text):
    return html.escape(str(text))


def _device_name(row):
    ## spruce's platform name (Brick, Flip, SmartProS) beats a SoC or board name.
    if row['platform'] and row['platform'].lower() not in row['device'].lower():
        return f"{row['device']} ({row['platform']})"

    return row['device']


def _hardware(row):
    ram = ""
    if row['ram_mb'].isdigit():
        ram_mb = int(row['ram_mb'])
        ram = f"{ram_mb // 1024} GB" if ram_mb >= 1024 else f"{ram_mb} MB"

    return " · ".join(part for part in (row['arch'], row['display'], ram) if part)


def _device_label(row):
    return f"{_device_name(row)} · {row['cfw']} {row['cfw_version']}".strip()


def render_html(rows, title="PortMaster Test Matrix", built=None):
    built = built or datetime.datetime.now()
    groups = group_rows(rows)
    failures = failure_index(rows)
    cfws = sorted({row['cfw'] for row in rows}, key=str.lower)
    devices = {device_key(row) for row in rows}
    builds = sorted({row['portmaster'] for row in rows if row['portmaster']})
    passing = sum(1 for runs in groups.values() if runs[0]['ok'])

    out = []
    add = out.append
    add(f"<title>{_e(title)}</title>")
    add('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    add('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&display=swap">')
    add(f"<style>{CSS}</style>")
    add('<div class="page">')

    ## Summary
    add("<header>")
    add(f"<h1>{_e(title)}</h1>")
    add(f'<p class="lede">PortMaster Test Suite reports from testers\' devices: the newest run of each CFW, version and device, '
        f'then every test that failed anywhere. Test builds: <span class="data">{_e(", ".join(builds) or "none")}</span>.</p>')
    add('<ul class="counts">')
    for number, label in ((len(rows), "reports"), (len(groups), "setups"), (len(devices), "devices"), (len(cfws), "CFWs"),
                          (passing, "setups passing"), (len(groups) - passing, "setups with failures")):
        add(f"<li><b>{number}</b><span>{label}</span></li>")
    add("</ul></header>")

    ## Coverage
    add('<section aria-labelledby="coverage"><h2 id="coverage">Coverage</h2>')
    add('<p class="lede">One row per CFW version and device, from its newest report. GUI shows whether those tests ran on the real screen or headless.</p>')
    add('<div class="scroll"><table><thead><tr><th>Device</th><th>Version</th><th>Python</th><th>SDL</th>')
    add("".join(f"<th>{_e(name)}</th>" for _, name in SECTIONS))
    add("<th>GUI ran</th><th>Build</th><th>Runs</th></tr></thead><tbody>")

    current_cfw = None
    for (cfw, cfw_version, _), runs in groups.items():
        if cfw != current_cfw:
            current_cfw = cfw
            add(f'<tr class="cfw"><th colspan="{len(SECTIONS) + 7}" scope="colgroup">{_e(cfw or "Unknown CFW")}</th></tr>')

        row = runs[0]
        version = _e(cfw_version)
        if row['os'] and row['os'].lower() not in (cfw_version.lower(), f"{cfw} {cfw_version}".lower()):
            version += f'<br><span class="muted">{_e(row["os"])}</span>'

        add(f'<tr><th scope="row">{_e(_device_name(row))}<br><span class="muted data">{_e(_hardware(row))}</span></th><td>{version}</td>')
        add(f'<td class="data">{_e(row["python"])}</td><td class="data">{_e(row["sdl"].replace("SDL ", "").replace(" ", "."))}</td>')
        for key, _ in SECTIONS:
            section = row['sections'].get(key)
            add(f"<td>{_chip(section['status'] if section else 'none')}</td>")
        add(f'<td>{_e(row["gui_how"] or "—")}</td><td class="data">{_e(row["portmaster"])}</td><td class="data">{len(runs)}</td></tr>')

    add("</tbody></table></div></section>")

    ## Failures
    add('<section aria-labelledby="failures"><h2 id="failures">Failures</h2>')
    if failures:
        add('<p class="lede">Each failing test once, with every setup it failed on, the most widespread first.</p><ul class="failures">')
        for test, message, found in failures:
            where = ", ".join(sorted({_device_label(row) for row in found}))
            add(f"<li><code>{_e(test)}</code><span>{_e(message)}</span><span class=\"where\">{len(found)} report{'s' if len(found) != 1 else ''}: {_e(where)}</span></li>")
        add("</ul>")
    else:
        add('<p class="empty">No failures in any report.</p>')
    add("</section>")

    ## Every run
    add('<section aria-labelledby="runs"><h2 id="runs">Every run</h2><div>')
    for row in rows:
        add(f"<details><summary>{_chip('pass' if row['ok'] else 'fail')}<strong>{_e(_device_label(row))}</strong>"
            f'<span class="muted data">{_e(row["started"])} · {_e(row["portmaster"])} · {_e(row["report"])}</span></summary>')
        add(f'<p class="muted">Python {_e(row["python"])}, {_e(row["sdl"])}, video drivers: {_e(" ".join(row["video_drivers"]) or "none")}'
            f'{"" if row["scrubbed"] else ". Not scrubbed (made before scrubbing)"}</p>')
        for key, section in row['sections'].items():
            add(f"<h3>{_chip(section['status'])} {_e(key)}: {_e(section['summary'])}</h3>")
            if section['details']:
                add(f"<pre>{_e(section['details'])}</pre>")
        add("</details>")
    add("</div></section>")

    add(f"<footer>Built {_e(built.strftime('%Y-%m-%d %H:%M'))} from {len(rows)} report{'s' if len(rows) != 1 else ''} by tools/test_suite/matrix.py.</footer>")
    add("</div>")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Coverage matrix from PortMaster Test Suite reports")
    parser.add_argument("folder", help="folder of report zips (searched recursively)")
    parser.add_argument("--out", default=".", help="where to write matrix.json and matrix.html")
    parser.add_argument("--title", default="PortMaster Test Matrix")
    options = parser.parse_args(argv)

    rows = read_reports(options.folder)
    out = Path(options.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "matrix.json").write_text(json.dumps(rows, indent=2))
    (out / "matrix.html").write_text(render_html(rows, options.title))
    print(f"{len(rows)} reports, {len(group_rows(rows))} setups -> {out / 'matrix.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
