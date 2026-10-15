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


def _small_text(zf, name, limit=64 * 1024):
    try:
        member = zf.getinfo(name)

    except KeyError:
        return ""

    return zf.read(member).decode("utf-8", "replace") if member.file_size <= limit else ""


def _sdl(info, probe_output):
    """("2.30.8" or "broken", warned): reports before the suite parsed it kept the probe's first line."""
    for text in (info.get('sdl'), *probe_output.splitlines()):
        match = re.match(r"SDL (\d+) (\d+) (\d+)$", str(text or "").strip())
        if match:
            return ".".join(match.groups()), bool(info.get('sdl_warning')) or "Warning" in probe_output or "Warning" in str(info.get('sdl'))

    return "broken", True


def _date(year, month, day=None):
    try:
        return datetime.date(int(year), int(month), int(day or 1)).isoformat()[:10 if day else 7]

    except ValueError:
        return ""


def release_date(cfw, cfw_version, os_release):
    """When the CFW version was released, "YYYY-MM-DD" (or "YYYY-MM"), "" if nothing says.

    From the version where it is a date (ROCKNIX 20260925, AmberELEC prerelease-20261003_1121,
    dArkOS 05102026, muOS 2601.0_JACARANDA), else the build date in os-release (knulli's
    OS_DATE, BUILD_DATE). spruce and RetroDECK have neither, and sort by version."""
    for match in re.finditer(r"(?<!\d)(\d{8})(?!\d)", cfw_version):
        digits = match.group(1)
        found = _date(digits[:4], digits[4:6], digits[6:]) or _date(digits[4:], digits[2:4], digits[:2])
        if found:
            return found

    match = re.match(r"(\d\d)(\d\d)(?:\.\d+)?(?:_|$)", cfw_version)
    if cfw.lower() == "muos" and match:
        found = _date(f"20{match.group(1)}", match.group(2))
        if found:
            return found

    values = dict(line.split("=", 1) for line in os_release.splitlines() if "=" in line)
    os_date = values.get("OS_DATE", "").strip('"\\ ')
    if re.match(r"\d{8}$", os_date):
        found = _date(os_date[:4], os_date[4:6], os_date[6:])
        if found:
            return found

    try:
        return datetime.datetime.strptime(" ".join(values.get("BUILD_DATE", "").strip('"\\ ').split()), "%a %b %d %H:%M:%S %Z %Y").date().isoformat()

    except ValueError:
        return ""


def version_key(version):
    """Natural order: 4.5.10 after 4.5.9."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.lower()) for part in re.findall(r"\d+|[^\d.\-_]+", version)]


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
            sdl_probe = _small_text(zf, "device/sdl.txt")
            os_release = _small_text(zf, "device/os-release.txt")

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
    row['sdl'], row['sdl_warned'] = _sdl(info, sdl_probe)
    ## device_info.txt before 0.2.3 called every knulli without a knulli.version "scarab".
    knulli_version = re.search(r"^VERSION=\"?([^\"\n]+)", os_release, re.M)
    if row['cfw'].lower() == "knulli" and row['cfw_version'] == "scarab" and knulli_version:
        row['cfw_version'] = _text(knulli_version.group(1).strip(), 40)
    ## Before spruce's own version file, device_info.txt fell back to the base system's
    ## (Buildroot 2021.11, Debian 13): not spruce's, the os column still shows it.
    if row['cfw'].lower() == "spruce" and not re.match(r"\d+\.\d+\.\d+", row['cfw_version']):
        row['cfw_version'] = "Unknown"
    ## Likewise dArkOS's version is its build date (05102026), older ones fell back to Debian's.
    if row['cfw'].lower() == "darkos" and not re.match(r"\d{8}$", row['cfw_version']):
        row['cfw_version'] = "Unknown"
    row['released'] = release_date(row['cfw'], row['cfw_version'], os_release)
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


def version_dates(groups):
    """{(cfw, cfw_version): sorted release dates of its devices' newest runs}: one version
    name can be several builds (knulli 42)."""
    dates = {}
    for (cfw, cfw_version, _), runs in groups.items():
        dates.setdefault((cfw, cfw_version), set())
        if runs[0].get('released'):
            dates[(cfw, cfw_version)].add(runs[0]['released'])

    return {key: sorted(found) for key, found in dates.items()}


def group_rows(rows):
    """{(cfw, cfw_version, device key): [rows, newest first]}: by CFW, its newest version first,
    then device. Versions go by release date, those without one after by version number, and
    an Unknown version last."""
    groups = {}
    for row in rows:
        groups.setdefault((row['cfw'], row['cfw_version'], device_key(row)), []).append(row)

    released = version_dates(groups)

    def newest_first(item):
        cfw, cfw_version, _ = item[0]
        dates = released[(cfw, cfw_version)]
        return (cfw_version not in ("", "Unknown"), dates[-1] if dates else "", version_key(cfw_version))

    ordered = sorted(groups.items(), key=lambda item: item[0][2].lower())
    ordered.sort(key=newest_first, reverse=True)
    ordered.sort(key=lambda item: item[0][0].lower())
    return dict(ordered)


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
tr.cfw th { background: var(--bg); font-family: var(--font-display); font-size: 1.05rem; color: var(--accent); padding-top: 14px; }
tr.version th { font-family: var(--font-data); font-size: 0.82rem; font-weight: 600; padding-left: 18px; }
tr.version .muted { font-family: var(--font-body); font-weight: 400; margin-left: 8px; }
th.device { padding-left: 32px; }
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


def _builds_line(builds):
    if not builds:
        return ""
    if len(builds) == 1:
        return f' Test build <span class="data">{_e(builds[0])}</span>.'
    return f' {len(builds)} test builds, <span class="data">{_e(builds[0])}</span> to <span class="data">{_e(builds[-1])}</span>.'


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
        f'then every test that failed anywhere.{_builds_line(builds)}</p>')
    add('<ul class="counts">')
    for number, label in ((len(rows), "reports"), (len(groups), "setups"), (len(devices), "devices"), (len(cfws), "CFWs"),
                          (passing, "setups passing"), (len(groups) - passing, "setups with failures")):
        add(f"<li><b>{number}</b><span>{label}</span></li>")
    add("</ul></header>")

    ## Coverage
    add('<section aria-labelledby="coverage"><h2 id="coverage">Coverage</h2>')
    add('<p class="lede">Each CFW, its versions newest release first, then one row per device from its newest report. '
        'GUI shows whether those tests ran on the real screen or headless.</p>')
    add('<div class="scroll"><table><thead><tr><th>Device</th><th>Python</th><th>SDL</th>')
    add("".join(f"<th>{_e(name)}</th>" for _, name in SECTIONS))
    add("<th>GUI ran</th><th>Build</th><th>Runs</th></tr></thead><tbody>")

    columns = len(SECTIONS) + 6
    released = version_dates(groups)
    current_cfw = current_version = None
    for (cfw, cfw_version, _), runs in groups.items():
        row = runs[0]
        if cfw != current_cfw:
            current_cfw, current_version = cfw, None
            add(f'<tr class="cfw"><th colspan="{columns}" scope="colgroup">{_e(cfw or "Unknown CFW")}</th></tr>')

        if cfw_version != current_version:
            current_version = cfw_version
            dates = released[(cfw, cfw_version)]
            notes = [f"released {dates[0]}" if len(dates) == 1 else f"builds from {dates[0]} to {dates[-1]}" if dates else ""]
            if row['os'] and row['os'].lower() not in (cfw_version.lower(), f"{cfw} {cfw_version}".lower()):
                notes.append(row['os'])
            note = " · ".join(_e(part) for part in notes if part)
            add(f'<tr class="version"><th colspan="{columns}" scope="colgroup">{_e(cfw_version or "Unknown version")}'
                f'{f" <span class=muted>{note}</span>" if note else ""}</th></tr>')

        add(f'<tr><th scope="row" class="device">{_e(_device_name(row))}<br><span class="muted data">{_e(_hardware(row))}</span></th>')
        sdl_note = '<br><span class="muted">warning</span>' if row['sdl_warned'] and row['sdl'] != "broken" else ""
        add(f'<td class="data">{_e(row["python"])}</td><td class="data">{_e(row["sdl"])}{sdl_note}</td>')
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
        add(f'<p class="muted">Python {_e(row["python"])}, SDL {_e(row["sdl"])}{" (with a load warning)" if row["sdl_warned"] and row["sdl"] != "broken" else ""}, video drivers: {_e(" ".join(row["video_drivers"]) or "none")}'
            f'{"" if row["scrubbed"] else ". Not scrubbed (made before scrubbing)"}</p>')
        for key, section in row['sections'].items():
            add(f"<h3>{_chip(section['status'])} {_e(key)}: {_e(section['summary'])}</h3>")
            ## The device section's details repeat the line above (older ones with pysdl2's warnings).
            if section['details'] and key != "device":
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
