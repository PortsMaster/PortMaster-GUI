#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# The coverage matrix for PortMaster Test Suite reports: which CFW / version / device
# combinations ran, how each section went, and which tests failed where.
#
#   python3 -I tools/test_suite/matrix.py <folder of report zips> [--out DIR] [--title TEXT]
#
# Writes DIR/matrix.json and DIR/matrix.html (self-contained, no scripts): a device x CFW
# release grid (devices named by devices.py), then every setup's newest run. Reports come
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import devices  # noqa: E402


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
    dArkOS 05102026 = 10 May, muOS 2601.0_JACARANDA), else the build date in os-release (knulli's
    OS_DATE, BUILD_DATE). spruce and RetroDECK have neither, and sort by version."""
    for match in re.finditer(r"(?<!\d)(\d{8})(?!\d)", cfw_version):
        digits = match.group(1)
        ## YYYYMMDD, or ArkOS and dArkOS's MMDDYYYY (their tags: v01302026 is 30 January).
        found = _date(digits[:4], digits[4:6], digits[6:]) or _date(digits[4:], digits[:2], digits[2:4])
        if found:
            return found

    match = re.match(r"(\d\d)(\d\d)(?:\.\d+)?(?:[_ ]|$)", cfw_version)
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


## knulli's releases and the day each came out (github.com/knulli-cfw/distribution and
## knulli-linux releases). A build gets the newest release out by its build date; alphas
## and dev builds call themselves "alpha" or by a Batocera version ("42", "44-dev").
KNULLI_RELEASES = (
    ("2024-05-09", "20240509"),
    ("2024-05-17", "20240517"),
    ("2024-05-30", "20240530"),
    ("2024-07-21", "20240721"),
    ("2024-12-04", "firefly"),
    ("2025-05-05", "gladiator"),
    ("2025-08-13", "gladiator II"),
    ("2026-05-11", "scarab"),
    )


def knulli_release(built):
    """(release name, its date) for a knulli built on `built` ("YYYY-MM-DD"), ("", "") if unknown."""
    found = ("", "")
    for released, name in KNULLI_RELEASES:
        if built and built >= released:
            found = (name, released)

    return found


## muOS's release names by version (muos.dev/release).
MUOS_RELEASES = {
    "2403.0": "Origin",
    "2405.0": "Beans", "2405.1": "Refried Beans", "2405.2": "Baked Beans",
    "2410.1": "Banana", "2410.2": "Big Banana", "2410.3": "AW Banana",
    "2502.0": "Pixie",
    "2508.0": "Goose", "2508.1": "Canada Goose", "2508.2": "Silly Goose", "2508.3": "Golden Goose", "2508.4": "Loose Goose",
    "2601.0": "Jacaranda", "2601.1": "Funky Jacaranda",
    "2606.0": "Andromeda",
    }


def muos_release(cfw_version, os_name):
    """ "2601.0 Jacaranda" for 2601.0_JACARANDA; "2410 Banana" for 2410 (os: "muOS 2410 Banana")."""
    match = re.match(r"(\d{4})(?:\.(\d+))?", cfw_version)
    if not match:
        return cfw_version

    if match.group(2) is not None:
        number = f"{match.group(1)}.{match.group(2)}"
        name = MUOS_RELEASES.get(number)
    else:
        number = match.group(1)
        ## No point release: the name the system gives, if it's one of that release's.
        names = {name for version, name in MUOS_RELEASES.items() if version.startswith(number + ".")}
        name = next((name for name in sorted(names, key=len, reverse=True) if name.lower() in os_name.lower()), None)
        ## Else the family, when they're all one (Banana, Big Banana, AW Banana).
        family = min(names, key=len) if names else None
        if name is None and family and all(other.endswith(family) for other in names):
            name = family

    return f"{number} {name}" if name else cfw_version


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
            cfw_files = _small_text(zf, "device/cfw-version.txt")

    except (OSError, KeyError, ValueError, zipfile.BadZipFile, UnicodeDecodeError):
        return None

    if not isinstance(data, dict) or not isinstance(data.get('info'), dict) or not isinstance(data.get('sections'), list):
        return None

    info = data['info']
    row = {key: _text(info.get(key)) for key in INFO_KEYS}
    reported_version = row['cfw_version']
    row['video_drivers'] = [_text(driver, 40) for driver in info.get('video_drivers', []) if isinstance(driver, str)][:20]
    ## Telling devices apart: DEVICE_NAME is just the SoC on some (sun50iw10: TrimUI Brick
    ## and MagicX Zero28). Reports from before the suite recorded these: environment.txt.
    row['platform'] = _text(info.get('platform') or environment.get("PLATFORM"), 60)
    row['model'] = _text(info.get('model'), 80)
    width, height = environment.get("DISPLAY_WIDTH"), environment.get("DISPLAY_HEIGHT")
    row['display'] = _text(info.get('display') or (f"{width}x{height}" if width and height else ""), 20)
    row['ram_mb'] = _text(info.get('ram_mb') or environment.get("DEVICE_RAM_MB"), 10)
    row['cpu'] = _text(environment.get("DEVICE_CPU"), 40)
    row['sdl'], row['sdl_warned'] = _sdl(info, sdl_probe)
    ## knulli: the release its build date falls in. The date from knulli's own version file
    ## ("scarab 2026/08/19 16:06", collected since 0669), Batocera's on gladiator and older,
    ## else os-release's OS_DATE. What the device called itself ("scarab" from device_info.txt
    ## before 0.2.3 whatever it was, "42", "alpha") isn't a release name. Development builds
    ## ("devel-8447a2c 2026/10/12 16:46") come after the newest release: "devel", by build date.
    knulli_date = ""
    if row['cfw'].lower() == "knulli":
        version_file = re.search(r"(?:knulli|batocera)\.version: (\S+) (\d{4})/(\d\d)/(\d\d)", cfw_files)
        built = _date(*version_file.groups()[1:]) if version_file else release_date(row['cfw'], "", os_release)
        name, knulli_date = knulli_release(built)
        if version_file and version_file.group(1).lower().startswith("devel") and built:
            name, knulli_date = "devel", built
        if name:
            row['cfw_version'] = name

    if row['cfw'].lower() == "muos":
        row['cfw_version'] = _text(muos_release(row['cfw_version'], row['os']), 40)

    ## AmberELEC's own VERSION (20211122) where older device_info.txt took CoreELEC's VERSION_ID (2021.01).
    amber_version = re.search(r'^VERSION="?([^"\n]+)', os_release, re.M)
    if row['cfw'].lower() == "amberelec" and amber_version:
        row['cfw_version'] = _text(amber_version.group(1).strip(), 60)

    ## Before spruce's own version file, device_info.txt fell back to the base system's
    ## (Buildroot 2021.11, Debian 13): not spruce's, the os column still shows it.
    if row['cfw'].lower() == "spruce" and not re.match(r"\d+\.\d+\.\d+", row['cfw_version']):
        row['cfw_version'] = "Unknown"
    ## Likewise ArkOS's and dArkOS's version is its release date (05102026), from the boot
    ## splash since device_info.txt 0.2.5. Older ones fell back to Ubuntu's or Debian's.
    if row['cfw'].lower() in ("arkos", "darkos", "darkosre") and not re.match(r"\d{8}(-\d+)?$", row['cfw_version']):
        row['cfw_version'] = "Unknown"
    row['released'] = knulli_date or release_date(row['cfw'], row['cfw_version'], os_release)
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

    ## The device line says what the device reported ("knulli 42 on trimui-brick-pro"):
    ## the version corrected above instead.
    device = row['sections'].get('device')
    reported = f"{row['cfw']} {reported_version} "
    if device and row['cfw_version'] != reported_version and device['summary'].startswith(reported):
        device['summary'] = f"{row['cfw']} {row['cfw_version']} (reported as {reported_version}) " + device['summary'][len(reported):]

    row['major_version'] = major_version(row)
    device = devices.identify(row)
    row['device_name'], row['maker'] = (device.name, device.maker) if device else ("", "")
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


## CFWs whose versions are dates (ROCKNIX 20261010, ArkOS 02012025-3, AmberELEC
## prerelease-20261003_1121): too many to list one by one, so they're grouped by month.
DATE_VERSIONED = ("arkos", "darkos", "darkosre", "rocknix", "jelos", "amberelec")


def version_group(row):
    """The version heading a row goes under: its version, or its release month ("2026-10")."""
    if row['cfw'].lower() in DATE_VERSIONED and row.get('released') and re.search(r"\d{8}", row['cfw_version']):
        return row['released'][:7]

    return row['cfw_version']


def muos_family(cfw_version):
    """ "Jacaranda" for 2601.1 Funky Jacaranda, "Banana" for 2410 Big Banana: the release, not its point releases."""
    match = re.match(r"(\d{4})(?:\.\d+)?\s*(.*)", cfw_version)
    if not match:
        return cfw_version

    number, name = match.groups()
    names = sorted({other for version, other in MUOS_RELEASES.items() if version.startswith(number + ".")}, key=len)
    return next((family for family in names if name.endswith(family)), name or number)


def major_version(row):
    """The grid's column for a row's version: muOS's and knulli's release names, the month for
    date-versioned CFWs (as version_group), else major.minor (spruce 4.5, RetroDECK 0.10).
    "?" when the version is unknown."""
    cfw, version = row['cfw'].lower(), row['cfw_version']
    if version in ("", "Unknown"):
        return "?"
    if cfw == "muos":
        return muos_family(version)
    if cfw in DATE_VERSIONED or cfw == "knulli":
        return version_group(row)

    match = re.match(r"v?(\d+)\.(\d+)", version)
    return f"{match.group(1)}.{match.group(2)}" if match else version


def version_dates(groups):
    """{(cfw, cfw_version): sorted release dates of its devices' newest runs}: one version
    name can be several builds (knulli scarab)."""
    dates = {}
    for (cfw, cfw_version, _), runs in groups.items():
        dates.setdefault((cfw, cfw_version), set())
        if runs[0].get('released'):
            dates[(cfw, cfw_version)].add(runs[0]['released'])

    return {key: sorted(found) for key, found in dates.items()}


def group_rows(rows):
    """{(cfw, version group, device key): [rows, newest first]}: by CFW, its newest version first,
    then device. Versions go by release date, those without one after by version number, and
    an Unknown version last."""
    groups = {}
    for row in rows:
        groups.setdefault((row['cfw'], version_group(row), device_key(row)), []).append(row)

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
## The device grid: a row per device (devices.py), a column per CFW release.
def grid_columns(rows, catalogue):
    """([(cfw, [major versions, newest first])] of the CFWs with reports, [CFWs without any that
    PortMaster-Info lists devices for])."""
    by_cfw = {}
    for row in rows:
        by_cfw.setdefault(row['cfw'], {}).setdefault(row['major_version'], []).append(row)

    def newest_first(item):
        major, runs = item
        dates = [run['released'] for run in runs if run.get('released')]
        return (major != "?", max(dates) if dates else "", version_key(major))

    tested = [(cfw, [major for major, _ in sorted(majors.items(), key=newest_first, reverse=True)])
              for cfw, majors in sorted(by_cfw.items(), key=lambda item: item[0].lower())]
    seen = {cfw.lower() for cfw in by_cfw}
    untested = sorted({cfw for device in catalogue for cfw in device.supported if cfw.lower() not in seen}, key=str.lower)
    return tested, untested


def grid_devices(rows, catalogue):
    """[(Device, [its rows])], by maker (Other last), family and name: every device with a report
    or that PortMaster-Info lists. A report no catalogue entry matches gets a row of its own."""
    by_name = {device.name: device for device in catalogue}
    found = {}
    for row in rows:
        device = by_name.get(row.get('device_name'))
        if device is None:
            name = _device_name(row) or "Unknown"
            device = by_name.setdefault(name, devices.Device(name, devices.OTHER))
        found.setdefault(device.name, (device, []))[1].append(row)

    for device in catalogue:
        if device.supported and device.name not in found:
            found[device.name] = (device, [])

    return sorted(found.values(), key=lambda item: (item[0].maker == devices.OTHER, item[0].maker.lower(),
                                                    (item[0].family or item[0].name).lower(), version_key(item[0].name)))


def cell_status(runs):
    """"fail" if a setup's newest run failed, "mixed" if only older ones did, else "pass"."""
    newest = {}
    for run in runs:
        newest.setdefault((version_group(run), device_key(run)), run)

    if not all(run['ok'] for run in newest.values()):
        return "fail"
    return "pass" if all(run['ok'] for run in runs) else "mixed"


def is_supported(device, cfw):
    return cfw.lower() in {name.lower() for name in device.supported}


def supported_pairs(found):
    """(device and CFW pairs PortMaster-Info lists that have a report, all it lists)."""
    pairs = {(device.name, cfw.lower()) for device, _ in found for cfw in device.supported}
    tested = {(device.name, run['cfw'].lower()) for device, runs in found for run in runs}
    return len(pairs & tested), len(pairs)


################################################################################
## The page
STATUS_LABEL = {"pass": "Pass", "fail": "Fail", "skip": "Skip", "info": "Info"}

CSS = """
/* Layout: one column, summary line, coverage table grouped by CFW, failures, then every run. */
:root {
  --bg: #f6f7f9; --surface: #ffffff; --fg: #1b2230; --muted: #5b6577; --line: #dde1e8;
  --accent: #2f5bd3;
  --pass: #1f7a4d; --pass-bg: #e3f3ea; --fail: #b3261e; --fail-bg: #fbe5e3; --skip: #6b6f7a; --skip-bg: #eceef2; --warn: #8a5a00; --warn-bg: #fdf0d2;
  --heat1: #d3ecdd; --heat2: #a9dbbd; --heat3: #6dbd8f; --heat4: #2f8a5a; --heat4-fg: #ffffff; --family: #edf6f0;
  --font-display: "Chakra Petch", "Segoe UI", system-ui, sans-serif;
  --font-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --font-data: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12161d; --surface: #1a2029; --fg: #e4e8ef; --muted: #9aa4b5; --line: #2c3442;
  --accent: #7d9cf0;
  --pass: #6fd29d; --pass-bg: #173326; --fail: #ff8a80; --fail-bg: #3a1c1a; --skip: #a3a9b5; --skip-bg: #252b35; --warn: #f2c46d; --warn-bg: #3a2e14;
  --heat1: #173326; --heat2: #1e4a33; --heat3: #2a6b47; --heat4: #3c9a64; --heat4-fg: #ffffff; --family: #18241d;
  color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #12161d; --surface: #1a2029; --fg: #e4e8ef; --muted: #9aa4b5; --line: #2c3442;
  --accent: #7d9cf0;
  --pass: #6fd29d; --pass-bg: #173326; --fail: #ff8a80; --fail-bg: #3a1c1a; --skip: #a3a9b5; --skip-bg: #252b35; --warn: #f2c46d; --warn-bg: #3a2e14;
  --heat1: #173326; --heat2: #1e4a33; --heat3: #2a6b47; --heat4: #3c9a64; --heat4-fg: #ffffff; --family: #18241d;
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
.gridwrap { display: grid; gap: 8px; }
.gridwrap > .controls { display: flex; flex-wrap: wrap; gap: 4px 20px; align-items: center; font-size: 0.85rem; }
.gridwrap > input { position: absolute; opacity: 0; pointer-events: none; }
.gridwrap > .controls label { display: inline-flex; gap: 8px; align-items: center; cursor: pointer; padding: 4px 12px 4px 8px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface); }
.gridwrap > .controls label::before { content: ""; width: 14px; height: 14px; border: 1.5px solid var(--muted); border-radius: 3px; box-sizing: border-box; }
#cfw-only:checked ~ .controls label[for="cfw-only"], #hide-untested:checked ~ .controls label[for="hide-untested"] { border-color: var(--accent); color: var(--accent); }
#cfw-only:checked ~ .controls label[for="cfw-only"]::before, #hide-untested:checked ~ .controls label[for="hide-untested"]::before { background: var(--accent); border-color: var(--accent); box-shadow: inset 0 0 0 2px var(--surface); }
#cfw-only:focus-visible ~ .controls label[for="cfw-only"], #hide-untested:focus-visible ~ .controls label[for="hide-untested"] { outline: 2px solid var(--accent); outline-offset: 2px; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 0.8rem; color: var(--muted); }
.legend span { display: inline-flex; gap: 6px; align-items: center; }
.legend span { gap: 2px; }
.legend span i:last-of-type { margin-right: 4px; }
.legend i { display: inline-block; width: 14px; height: 14px; border-radius: 3px; }
.gridbox { max-height: 80vh; overflow: auto; }
table.grid { width: auto; border-collapse: separate; border-spacing: 0; font-size: 0.78rem; }
.grid th, .grid td { padding: 0; border: 0; border-bottom: 1px solid var(--line); vertical-align: middle; text-align: center; }
.grid td.c, .grid td.v, .grid td.t, .grid td.u { width: 26px; min-width: 26px; height: 24px; font-family: var(--font-data); font-variant-numeric: tabular-nums; }
.grid .first { border-left: 1px solid var(--line); }
.grid thead th { position: sticky; top: 0; z-index: 2; background: var(--surface); }
.grid thead tr.cfws th { height: 26px; color: var(--accent); font-family: var(--font-display); font-size: 0.8rem; text-transform: none; letter-spacing: 0; }
.grid thead tr.cfws th:not(.dev) { white-space: nowrap; padding: 0 4px; font-size: 0.75rem; }
.grid thead tr.majors th { top: 27px; padding: 6px 0; font-family: var(--font-data); font-size: 0.72rem; text-transform: none; letter-spacing: 0; color: var(--fg); font-weight: 500; }
.grid thead tr.majors th span { writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; }
.grid thead th.u span, .grid thead th.t span { color: var(--muted); }
.grid .dev { position: sticky; left: 0; z-index: 1; background: var(--surface); text-align: left; white-space: nowrap; padding: 0 12px 0 10px; border-right: 1px solid var(--line); font-weight: 400; }
.grid thead .dev { z-index: 3; vertical-align: bottom; padding-bottom: 6px; }
.grid tr.maker th { color: var(--accent); font-family: var(--font-display); font-weight: 600; padding-top: 8px; }
.grid tr.maker td { background: var(--bg); }
.grid tr.maker th.dev { background: var(--bg); }
.grid tr.familyrow th.dev { font-weight: 600; }
.grid tr.member th.dev { padding-left: 24px; }
.grid td.n, .grid th.n { padding: 0 8px; font-family: var(--font-data); color: var(--muted); border-left: 1px solid var(--line); }
.grid tfoot th, .grid tfoot td { color: var(--muted); font-family: var(--font-data); border-bottom: 0; }
.grid tfoot th.dev { font-family: var(--font-body); }
.grid a { color: inherit; text-decoration: none; display: block; line-height: 24px; }
.grid a:hover { text-decoration: underline; }
.c.h1, .legend .h1 { background: var(--heat1); }
.c.h2, .legend .h2 { background: var(--heat2); }
.c.h3, .legend .h3 { background: var(--heat3); }
.c.h4, .legend .h4 { background: var(--heat4); color: var(--heat4-fg); }
.c.fail, .legend .fail { background: var(--fail-bg); color: var(--fail); font-weight: 600; box-shadow: inset 0 0 0 2px var(--fail); }
.c.mixed, .legend .mixed { box-shadow: inset 0 -3px 0 var(--warn); }
.c.family, .legend .family { background: var(--family); }
.c.gap::after, .legend .gap { content: ""; display: inline-block; width: 10px; height: 10px; border: 1.5px dashed var(--muted); border-radius: 50%; box-sizing: border-box; }
.legend .gap { width: 14px; height: 14px; }
.grid .t { display: none; }
#cfw-only:checked ~ .gridbox .v { display: none; }
#cfw-only:checked ~ .gridbox .t { display: table-cell; }
#hide-untested:checked ~ .gridbox tr.untested, #hide-untested:checked ~ .gridbox .u { display: none; }
tr:target > th, tr:target > td { background: var(--warn-bg); }
.chip { display: inline-block; min-width: 3.4em; text-align: center; padding: 1px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
.chip.pass { color: var(--pass); background: var(--pass-bg); }
.chip.fail { color: var(--fail); background: var(--fail-bg); }
.chip.skip, .chip.info, .chip.none { color: var(--skip); background: var(--skip-bg); }
.failures { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.failures li { background: var(--surface); border: 1px solid var(--line); border-left: 3px solid var(--fail); border-radius: 6px; padding: 10px 14px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; min-width: 0; overflow-wrap: anywhere; }
.failures code { font-family: var(--font-data); font-size: 0.8rem; overflow-wrap: anywhere; }
.failures .where { color: var(--muted); font-size: 0.85rem; }
.empty { color: var(--muted); margin: 0; }
details { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 8px 14px; }
details + details { margin-top: 8px; }
section > div, details { min-width: 0; overflow-wrap: anywhere; }
summary .data { white-space: normal; }
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


def heat(count):
    """How well covered a cell is, 1 to 4: one report, a few, several, many."""
    return 1 if count <= 1 else 2 if count <= 3 else 3 if count <= 7 else 4


CELL_STATUS = {"pass": "all passing", "fail": "failing", "mixed": "passing now, failed before"}


def _cell_title(name, cfw, major, runs, status):
    lines = [f"{name} · {cfw} {major}".rstrip(), f"{len(runs)} report{'s' if len(runs) != 1 else ''}, {CELL_STATUS[status]}"]
    lines.append("Versions: " + ", ".join(sorted({run['cfw_version'] for run in runs}, key=version_key, reverse=True)))
    builds = sorted({run['portmaster'] for run in runs if run['portmaster']})
    if builds:
        lines.append("Builds: " + (builds[0] if len(builds) == 1 else f"{builds[0]} to {builds[-1]}"))
    lines.append("Reported as: " + ", ".join(sorted({_device_name(run) for run in runs})))
    return "\n".join(lines)


def _grid_cell(classes, name, cfw, major, runs, supported, setup_ids, family_runs=()):
    if runs:
        status = cell_status(runs)
        target = setup_ids.get(id(runs[0]))
        number = f'<a href="#{target}">{len(runs)}</a>' if target else str(len(runs))
        return f'<td class="{classes} c {status} h{heat(len(runs))}" title="{_e(_cell_title(name, cfw, major, runs, status))}">{number}</td>'

    title = []
    if family_runs:
        classes += " c family"
        title.append(f"No reports, but {len(family_runs)} from its family: " + ", ".join(sorted({run['device_name'] for run in family_runs})))
    if supported:
        classes += " c gap" if " c " not in f" {classes} " else " gap"
        title.append("Supported per PortMaster-Info, no reports")
    if title:
        return f'<td class="{classes}" title="{_e(f"{name} · {cfw} {major}".rstrip() + chr(10) + chr(10).join(title))}"></td>'
    return f'<td class="{classes}"></td>'


def render_grid(add, rows, catalogue, setup_ids):
    """The device x CFW release grid: report counts, coloured by how the newest runs went.
    CSS only: the checkboxes switch to one column per CFW and hide untested rows."""
    tested, untested = grid_columns(rows, catalogue)
    found = grid_devices(rows, catalogue)
    ## (classes, cfw, major or None): a column per release, one per CFW (CFWs-only view), untested CFWs.
    ## PortMaster-Info's support has no versions: an untested device shows as a gap under the
    ## CFW's newest release only (where a report would help), not under every older one.
    columns = []
    for cfw, majors in tested:
        columns.extend((("v first" if index == 0 else "v"), cfw, major) for index, major in enumerate(majors))
        columns.append(("t first", cfw, None))
    columns.extend(("u first", cfw, None) for cfw in untested)

    ## (Not knulli's development builds: a gap is for the newest release.)
    latest = {cfw: next((major for major in majors if major not in ("?", "devel")), majors[0]) for cfw, majors in tested}
    with_reports, listed = supported_pairs(found)
    releases = sum(len(majors) for _, majors in tested)
    add('<section aria-labelledby="grid"><h2 id="grid">Devices</h2>')
    add(f'<p class="lede">How many reports each device has on each CFW release: {sum(1 for _, runs in found if runs)} devices on {releases} CFW releases. '
        f'Of the {listed} device and CFW pairs PortMaster-Info lists, {with_reports} have a report; the others are marked under each CFW\'s newest release. '
        'Hover over a cell for its versions and builds, select its number to see its newest run.</p>')
    add('<div class="gridwrap"><input type="checkbox" id="cfw-only"><input type="checkbox" id="hide-untested">'
        '<div class="controls"><label for="cfw-only">One column per CFW</label><label for="hide-untested">Only devices and CFWs with reports</label></div>')
    add('<div class="legend"><span><i class="h1"></i><i class="h2"></i><i class="h3"></i><i class="h4"></i>1, 2-3, 4-7, 8+ reports, passing</span>'
        '<span><i class="c fail"></i>newest run failing</span><span><i class="h2 c mixed"></i>passing now, failed before</span>'
        '<span><i class="family"></i>no reports, but its family has</span><span><i class="gap"></i>supported, no reports</span></div>')
    add('<div class="scroll gridbox"><table class="grid"><thead><tr class="cfws"><th class="dev" rowspan="2" scope="col">Device</th>')
    for cfw, majors in tested:
        add(f'<th class="v first" colspan="{len(majors)}" scope="colgroup">{_e(cfw)}</th><th class="t first"></th>')
    add("".join('<th class="u first"></th>' for _ in untested))
    add('<th class="n" rowspan="2" scope="col">Reports</th></tr><tr class="majors">')
    for classes, cfw, major in columns:
        label = major if major is not None else cfw
        heading = f"{cfw} {major}" if major is not None else cfw
        add(f'<th class="{classes}" scope="col" title="{_e(heading)}"><span>{_e(label)}</span></th>')
    add("</tr></thead><tbody>")

    def in_column(runs, cfw, major):
        return [run for run in runs if run['cfw'] == cfw and (major is None or run['major_version'] == major)]

    def cells(name, runs, supported, family_runs=()):
        out = []
        for classes, cfw, major in columns:
            newest = major is None or major == latest.get(cfw)
            out.append(_grid_cell(classes, name, cfw, major or "", in_column(runs, cfw, major), newest and supported(cfw), setup_ids,
                                  in_column(family_runs, cfw, major)))
        return "".join(out) + f'<td class="n">{len(runs) or ""}</td>'

    maker = family = None
    family_runs = []
    for device, runs in found:
        if device.maker != maker:
            maker, family = device.maker, None
            reported = any(runs for other, runs in found if other.maker == maker)
            add(f'<tr class="maker{"" if reported else " untested"}"><th class="dev" scope="rowgroup">{_e(maker)}</th>')
            add("".join(f'<td class="{classes}"></td>' for classes, _, _ in columns) + '<td class="n"></td></tr>')

        if device.family and device.family != family:
            family = device.family
            members = [(other, other_runs) for other, other_runs in found if other.family == family]
            family_runs = [run for _, member_runs in members for run in member_runs]
            label = family[len(maker) + 1:] if family.startswith(maker + " ") else family
            add(f'<tr class="familyrow{"" if family_runs else " untested"}"><th class="dev" scope="row" title="{_e(family)}">{_e(label)}</th>')
            add(cells(family, family_runs, lambda cfw: any(is_supported(other, cfw) for other, _ in members)) + "</tr>")
        elif not device.family:
            family, family_runs = None, []

        name = device.short_name if device.maker != devices.OTHER else device.name
        member = " member" if device.family else ""
        add(f'<tr class="{"" if runs else "untested"}{member}"><th class="dev" scope="row" title="{_e(device.name)}">{_e(name)}</th>')
        add(cells(device.name, runs, lambda cfw: is_supported(device, cfw), [run for run in family_runs if run not in runs]) + "</tr>")

    add('</tbody><tfoot><tr><th class="dev" scope="row">Reports</th>')
    for classes, cfw, major in columns:
        count = sum(1 for row in rows if row['cfw'] == cfw and (major is None or row['major_version'] == major))
        add(f'<td class="{classes}">{count or ""}</td>')
    add(f'<td class="n">{len(rows)}</td></tr></tfoot></table></div></div></section>')


def render_html(rows, title="PortMaster Test Matrix", built=None, catalogue=None):
    built = built or datetime.datetime.now()
    groups = group_rows(rows)
    failures = failure_index(rows)
    cfws = sorted({row['cfw'] for row in rows}, key=str.lower)
    hardware = {row["device_name"] or _device_name(row) for row in rows}
    builds = sorted({row['portmaster'] for row in rows if row['portmaster']})
    passing = sum(1 for runs in groups.values() if runs[0]['ok'])
    setup_ids = {id(run): f"setup-{number}" for number, runs in enumerate(groups.values()) for run in runs}

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
    for number, label in ((len(rows), "reports"), (len(groups), "setups"), (len(hardware), "devices"), (len(cfws), "CFWs"),
                          (passing, "setups passing"), (len(groups) - passing, "setups with failures")):
        add(f"<li><b>{number}</b><span>{label}</span></li>")
    add("</ul></header>")

    render_grid(add, rows, devices.catalogue() if catalogue is None else catalogue, setup_ids)

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

        by_month = cfw_version != row['cfw_version']
        if cfw_version != current_version:
            current_version = cfw_version
            dates = released[(cfw, cfw_version)]
            if by_month:
                ## Every version tested that month, newest first.
                versions = sorted({run[0]['cfw_version'] for (other_cfw, group, _), run in groups.items() if (other_cfw, group) == (cfw, cfw_version)},
                                  key=version_key, reverse=True)
                versions.sort(key=lambda version: release_date(cfw, version, ""), reverse=True)
                notes = [", ".join(versions)]
            else:
                notes = [f"released {dates[0]}" if len(dates) == 1 else f"builds from {dates[0]} to {dates[-1]}" if dates else ""]
            ## (knulli's os-release names the Batocera it's built on, not knulli.)
            if row['os'] and not by_month and cfw.lower() != "knulli" and cfw_version.split(" ")[0].lower() not in row['os'].lower():
                notes.append(row['os'])
            note = " · ".join(_e(part) for part in notes if part)
            add(f'<tr class="version"><th colspan="{columns}" scope="colgroup">{_e(cfw_version or "Unknown version")}'
                f'{f" <span class=muted>{note}</span>" if note else ""}</th></tr>')

        hardware = _hardware(row) + (f" · {row['cfw_version']}" if by_month else "")
        add(f'<tr id="{setup_ids[id(row)]}"><th scope="row" class="device">{_e(_device_name(row))}<br><span class="muted data">{_e(hardware)}</span></th>')
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
    unknown = sorted({_device_name(row) for row in rows if not row['device_name']})
    if unknown:
        print(f"Not in devices.py, listed under {devices.OTHER}: {', '.join(unknown)}", file=sys.stderr)
    out = Path(options.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "matrix.json").write_text(json.dumps(rows, indent=2))
    (out / "matrix.html").write_text(render_html(rows, options.title))
    print(f"{len(rows)} reports, {len(group_rows(rows))} setups -> {out / 'matrix.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
