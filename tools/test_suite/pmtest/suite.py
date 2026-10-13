# SPDX-License-Identifier: MIT
#
# The PortMaster Test Suite: installs the PortMaster build it ships with, runs every
# test there is on this device, shows a summary and writes a report zip for the devs.
#
# Run by "PortMaster Test Suite.sh" with the device's python (3.7+). Standard library
# only; pytest comes from site/, the code under test from tree/.
#
#   suite.py [--no-ui] [--skip install,pytest,gui,smoke,interactive] [--controlfolder DIR]

import argparse
import datetime
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fifo import Dialog  # noqa: E402


HERE = Path(__file__).resolve().parent
TREE = HERE / "tree"
SITE = HERE / "site"
PM_ZIP = HERE / "PortMaster.zip"
REPORTS = HERE / "reports"

STEPS = ("install", "device", "pytest", "gui", "smoke", "interactive")

SMOKE_PORT = "unlevel.zip"
SMOKE_SCRIPT = "Unlevel.sh"

PASS, FAIL, SKIP, INFO = "pass", "fail", "skip", "info"
LABELS = {PASS: "PASS", FAIL: "FAIL", SKIP: "SKIP", INFO: "INFO"}


################################################################################
## Results
class Section:
    def __init__(self, key, name):
        self.key = key
        self.name = name
        self.status = SKIP
        self.summary = "not run"
        self.details = ""
        self.seconds = 0.0

    def set(self, status, summary, details=""):
        self.status = status
        self.summary = summary
        self.details = details

    def to_dict(self):
        return {
            'key': self.key, 'name': self.name, 'status': self.status,
            'summary': self.summary, 'details': self.details, 'seconds': round(self.seconds, 1),
            }


def parse_junit(junit_file, max_failures=20):
    """
    Counts and the failed tests from pytest's JUnit XML:
    {'tests', 'passed', 'failed', 'errors', 'skipped', 'failures': [(test id, first line)], 'skip_reasons': {reason: n}}
    """
    result = {'tests': 0, 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0, 'failures': [], 'skip_reasons': {}}

    root = ET.parse(str(junit_file)).getroot()
    for case in root.iter('testcase'):
        result['tests'] += 1
        test_id = f"{case.get('classname', '')}::{case.get('name', '')}"

        failure = case.find('failure')
        error = case.find('error')
        skipped = case.find('skipped')

        if failure is not None or error is not None:
            node = failure if failure is not None else error
            result['failed' if failure is not None else 'errors'] += 1
            first_line = (node.get('message') or node.text or "").strip().splitlines()[:1]
            if len(result['failures']) < max_failures:
                result['failures'].append((test_id, first_line[0] if first_line else ""))

        elif skipped is not None:
            result['skipped'] += 1
            reason = (skipped.get('message') or "").strip()
            result['skip_reasons'][reason] = result['skip_reasons'].get(reason, 0) + 1

        else:
            result['passed'] += 1

    return result


def junit_summary(result):
    text = f"{result['passed']} passed, {result['failed'] + result['errors']} failed, {result['skipped']} skipped"
    details = []
    if result['failures']:
        details.append("Failed:")
        details.extend(f"- {test_id}: {line}" for test_id, line in result['failures'])

    if result['skip_reasons']:
        details.append("Skipped:")
        details.extend(f"- {count} x {reason}" for reason, count in sorted(result['skip_reasons'].items(), key=lambda item: -item[1]))

    return text, "\n".join(details)


## The button checks: key, what it checks, the prompt, and the expected answer
## (True: accepts, False: cancels, None: the physical A/B pair, which must differ).
BUTTON_CHECKS = (
    ("labelled_ok", "the OKAY button", "Press the button shown next to OKAY at the bottom of the screen.", True),
    ("labelled_cancel", "the CANCEL button", "Press the button shown next to CANCEL at the bottom of the screen.", False),
    ("physical_a", "the A button", "Press the button printed with A on your device.", None),
    ("physical_b", "the B button", "Press the button printed with B on your device.", None),
    )


def button_verdict(attempts):
    """
    attempts: {check key: [answer, ...]}, answers True (accepted) / False (cancelled), a
    second answer only after a retry. Returns (problems, notes); the last answer counts.
    """
    def last(key):
        return (attempts.get(key) or [None])[-1]

    problems = []
    notes = []

    for key, name, _, expected in BUTTON_CHECKS:
        if expected is None:
            continue

        if last(key) is not expected:
            problems.append(f"{name} did not {'accept' if expected else 'cancel'}")
        elif len(attempts.get(key, [])) > 1:
            notes.append(f"{name}: right on the second try")

    physical_a, physical_b = last("physical_a"), last("physical_b")
    if physical_a is None or physical_b is None or physical_a == physical_b:
        problems.append("the A and B buttons did the same thing")
    else:
        notes.append(f"The physical {'A' if physical_a else 'B'} button accepts.")
        if len(attempts.get("physical_a", [])) > 1:
            notes.append("A / B: right on the second try")

    return problems, notes


def merge_results(results):
    """Adds up several parse_junit results ({'error': ...} for a run that didn't finish)."""
    merged = {'tests': 0, 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0, 'failures': [], 'skip_reasons': {}, 'error': ""}
    for result in results:
        if result is None or 'error' in result:
            merged['errors'] += 1
            merged['error'] += (result or {}).get('error', "pytest didn't run") + "\n"
            continue

        for key in ('tests', 'passed', 'failed', 'errors', 'skipped'):
            merged[key] += result[key]

        merged['failures'].extend(result['failures'])
        for reason, count in result['skip_reasons'].items():
            merged['skip_reasons'][reason] = merged['skip_reasons'].get(reason, 0) + count

    return merged


def set_from_results(section, results, suffix=""):
    """A section's status from pytest runs: FAIL on any failure, SKIP if nothing ran."""
    result = merge_results(results)
    text, details = junit_summary(result)
    if result['error']:
        details = (result['error'].strip() + "\n" + details).strip()

    if result['failed'] or result['errors']:
        section.set(FAIL, text + suffix, details)
    elif result['passed'] == 0:
        ## Nothing ran (eg: no SDL at all): not a pass.
        section.set(SKIP, "not run: " + text, details)
    else:
        section.set(PASS, text + suffix, details)


def summary_entries(sections, report_name):
    """The summary screen: an overall line, one per section, then where the report is."""
    ran = [section for section in sections if section.status in (PASS, FAIL)]
    failed = [section for section in ran if section.status == FAIL]

    if failed:
        overall = f"{len(failed)} of {len(ran)} checks failed"
        overall_desc = "Failed: " + ", ".join(section.name for section in failed) + \
            f".\n\nPlease send the report to the PortMaster devs:\n{report_name}"
    else:
        overall = f"All {len(ran)} checks passed"
        overall_desc = f"Thanks for testing! The report is saved as:\n{report_name}"

    entries = [("#overall", overall, overall_desc)]
    for section in sections:
        description = section.summary
        if section.details:
            description += "\n\n" + section.details

        entries.append((section.key, f"{LABELS[section.status]}: {section.name}", description))

    entries.append(("#report", "Report", f"Saved as:\n{report_name}\n\nIn the PortMaster Test Suite's reports folder."))
    return entries


def summary_text(sections, info):
    lines = ["PortMaster Test Suite", "=" * 21, ""]
    for key in ("portmaster", "cfw", "device", "python", "started"):
        if key in info:
            lines.append(f"{key:<11}: {info[key]}")

    lines.append("")
    for section in sections:
        lines.append(f"[{LABELS[section.status]}] {section.name}: {section.summary} ({section.seconds:.0f}s)")
        if section.details:
            lines.extend("        " + line for line in section.details.splitlines())

    return "\n".join(lines) + "\n"


def report_name(info, when):
    def clean(text):
        return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("_") or "unknown"

    return f"{clean(info.get('cfw', 'cfw'))}-{clean(info.get('device', 'device'))}-{when.strftime('%Y%m%d-%H%M')}.zip"


def write_report(zip_path, work_dir, sections, info, extra_files=()):
    """Everything in work_dir, the summary, and extra_files [(path, name in zip)]."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.txt", summary_text(sections, info))
        zf.writestr("summary.json", json.dumps({
            'info': info, 'sections': [section.to_dict() for section in sections]}, indent=2))

        for path in sorted(work_dir.rglob("*")):
            if path.is_file() and path.name not in ("progress", "pm_input", "pm_done") and "scratch" not in path.parts:
                zf.write(str(path), str(path.relative_to(work_dir)))

        for path, name in extra_files:
            if Path(path).is_file():
                zf.write(str(path), name)

    return zip_path


def pick_work_dir(candidates, need_bytes=300 * 1024 * 1024):
    """The first candidate directory with room, the last one otherwise."""
    for candidate in candidates:
        try:
            Path(candidate).mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(str(candidate)).free >= need_bytes:
                return Path(candidate)

        except OSError:
            continue

    Path(candidates[-1]).mkdir(parents=True, exist_ok=True)
    return Path(candidates[-1])


################################################################################
## The run
class Suite:
    def __init__(self, options):
        self.options = options
        self.started = datetime.datetime.now()
        self.controlfolder = Path(options.controlfolder or os.environ.get("controlfolder", "/roms/ports/PortMaster"))
        self.work = pick_work_dir([Path(tempfile.gettempdir()) / "pmtest", HERE / "work"])
        if self.work.exists():
            shutil.rmtree(str(self.work), ignore_errors=True)

        self.work.mkdir(parents=True, exist_ok=True)
        self.log_file = self.work / "run.log"
        self.info = {'started': self.started.isoformat(timespec='seconds')}
        self.sections = [Section(key, name) for key, name in (
            ("install", "Install PortMaster"),
            ("device", "Device information"),
            ("pytest", "Test suite"),
            ("gui", "GUI tests"),
            ("smoke", "Online install test"),
            ("interactive", "Button and message checks"),
            )]

        self.ui = Dialog(self.controlfolder, self.work / "fifo", log=self.log)
        self.has_ui = False

    ## Helpers.
    def log(self, text):
        line = f"{datetime.datetime.now().strftime('%H:%M:%S')} {text}"
        print(line, flush=True)
        with open(str(self.log_file), "a") as fh:
            fh.write(line + "\n")

    def section(self, key):
        for section in self.sections:
            if section.key == key:
                return section

        raise KeyError(key)

    def run(self, command, timeout=600, env=None, cwd=None, output=None):
        """(return code, output text). Never raises; a timeout is return code -9."""
        self.log("run: " + " ".join(str(part) for part in command))
        try:
            result = subprocess.run(
                [str(part) for part in command], env=env, cwd=None if cwd is None else str(cwd), timeout=timeout,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            code, text = result.returncode, result.stdout.decode("utf-8", "replace")

        except subprocess.TimeoutExpired as err:
            code, text = -9, (err.stdout or b"").decode("utf-8", "replace") + f"\n[timed out after {timeout}s]"

        except OSError as err:
            code, text = -1, f"[unable to run: {err}]"

        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text)

        return code, text

    def say(self, text):
        self.log(text)
        if self.has_ui:
            self.ui.message(text)

    def ui_start(self):
        self.has_ui = (not self.options.no_ui) and self.ui.start("--no-check")
        if self.has_ui:
            self.ui.messages_begin()

        return self.has_ui

    def ui_stop(self):
        if self.has_ui:
            self.ui.stop()

        self.has_ui = False

    def test_env(self, **extra):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(SITE), str(HERE)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.setdefault("PYSDL2_DLL_PATH", "/usr/lib")
        env.update(extra)
        return env

    ## Steps.
    def step_install(self, section):
        version = zipfile.ZipFile(str(PM_ZIP)).read("PortMaster/version").decode().strip()
        self.info['portmaster'] = version
        self.say(f"Installing PortMaster {version}, this takes a minute.")

        installed = self.ui.install(PM_ZIP) if self.has_ui else None
        if installed is None:
            ## No screen: the installed harbourmaster does it.
            code, text = self.run(
                [sys.executable, self.controlfolder / "harbourmaster", "--no-check", "install", str(PM_ZIP)],
                timeout=1800, cwd=self.controlfolder, output=self.work / "install" / "harbourmaster.txt")
            installed = code == 0

        ## The new PortMaster's pugwash from here on (its first run does the post-install step).
        self.ui_stop()
        self.ui_start()

        now = (self.controlfolder / "version").read_text().strip() if (self.controlfolder / "version").is_file() else "?"
        if installed and now == version:
            section.set(PASS, f"PortMaster {version} installed")
        else:
            section.set(FAIL, f"PortMaster {version} did not install (now {now})", "See install/ and the PortMaster logs in the report.")

    def step_device(self, section):
        out = self.work / "device"
        out.mkdir(parents=True, exist_ok=True)

        self.info['python'] = platform.python_version()
        self.info['uname'] = " ".join(platform.uname())
        self.info['cfw'] = os.environ.get("CFW_NAME", "unknown")
        self.info['cfw_version'] = os.environ.get("CFW_VERSION", "")
        self.info['device'] = os.environ.get("DEVICE_NAME", platform.node())
        self.info['arch'] = os.environ.get("DEVICE_ARCH", platform.machine())

        (out / "environment.txt").write_text("".join(
            f"{key}={value}\n" for key, value in sorted(os.environ.items())
            if key.split("_")[0] in ("CFW", "DEVICE", "DISPLAY", "SDL", "PYSDL2", "LD", "PATH", "ESUDO", "ANALOG", "XDG", "HOME", "PM", "controlfolder", "directory", "CUR")))

        for name, command in (
                ("os-release", ["cat", "/etc/os-release"]),
                ("uname", ["uname", "-a"]),
                ("mounts", ["cat", "/proc/mounts"]),
                ("df", ["df", "-h"]),
                ("meminfo", ["cat", "/proc/meminfo"]),
                ("dmesg", ["sh", "-c", "dmesg | tail -n 300"]),
                ("launcher", ["sh", "-c", f"ls -la '{self.controlfolder}/..' '{self.controlfolder}/utils'; tail -n 3 '{self.controlfolder}/PortMaster.sh' 2>/dev/null"]),
                ):
            self.run(command, timeout=30, output=out / f"{name}.txt")

        self.run(
            [sys.executable, self.controlfolder / "harbourmaster", "--no-check", "device_info"],
            timeout=120, cwd=self.controlfolder, output=out / "harbourmaster-device_info.txt")

        ## Which SDL libraries load, through the same sdl2 package pugwash uses.
        probe = (
            "import sdl2, sdl2.sdlimage, sdl2.sdlttf, sdl2.sdlmixer\n"
            "v = sdl2.SDL_version(); sdl2.SDL_GetVersion(v)\n"
            "print('SDL', v.major, v.minor, v.patch)\n"
            "print('DRIVERS', ' '.join(sdl2.SDL_GetVideoDriver(i).decode() for i in range(sdl2.SDL_GetNumVideoDrivers())))\n")
        code, text = self.run(
            [sys.executable, "-c", probe], timeout=60,
            env=self.test_env(PYTHONPATH=str(TREE / "PortMaster" / "exlibs")), output=out / "sdl.txt")

        drivers = []
        for line in text.splitlines():
            if line.startswith("DRIVERS "):
                drivers = line.split()[1:]

        self.info['video_drivers'] = drivers
        self.info['sdl'] = (text.strip().splitlines() or ["?"])[0] if code == 0 else "not loadable"

        section.set(INFO, f"{self.info['cfw']} {self.info['cfw_version']} on {self.info['device']} ({self.info['arch']}), Python {self.info['python']}",
                    f"{self.info['sdl']}, video drivers: {' '.join(drivers) or 'none'}")

    def _pytest(self, name, marker, timeout, extra_env=None, label="Testing"):
        """Runs pytest on the tree; parse_junit's result, or {'error': ...} if it didn't finish."""
        out = self.work / name
        out.mkdir(parents=True, exist_ok=True)
        progress = self.work / "progress"
        if progress.exists():
            progress.unlink()

        junit = out / "junit.xml"

        command = [
            sys.executable, "-m", "pytest", "-p", "pmtest_plugin", "-p", "no:cacheprovider",
            "-q", "-rfEs", "--tb=short", "-m", marker, f"--junitxml={junit}"]

        env = self.test_env(PMTEST_PROGRESS=str(progress), **(extra_env or {}))
        self.log(f"pytest ({name}): " + " ".join(command) + f" {extra_env or ''}")
        started = time.monotonic()
        with open(str(out / "output.txt"), "w") as output:
            proc = subprocess.Popen(command, cwd=str(TREE), env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)

            last = None
            while proc.poll() is None:
                if time.monotonic() - started > timeout:
                    proc.kill()
                    self.log(f"pytest: timed out after {timeout}s")
                    break

                try:
                    done, total = progress.read_text().split()[:2]
                except (OSError, ValueError):
                    done, total = "0", "0"

                if self.has_ui and (done, total) != last and total != "0":
                    self.ui.progress(f"{label} ({done}/{total})", int(done), int(total))
                    last = (done, total)

                time.sleep(1)

            proc.wait()

        if self.has_ui:
            self.ui.progress_clear()

        if not junit.is_file():
            return {'error': f"pytest didn't finish (exit {proc.returncode})\n" + self._tail(out / "output.txt")}

        return parse_junit(junit)

    @staticmethod
    def _tail(path, lines=15):
        try:
            return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return ""

    def step_pytest(self, section):
        self.say("Running the test suite. This can take a few minutes.")
        set_from_results(section, [self._pytest("pytest", "not sdl and not network", timeout=2400)])

    def step_gui(self, section):
        drivers = self.info.get('video_drivers', [])

        ## Headless where SDL can, otherwise the real screen: pugwash lets go of it first.
        if "dummy" in drivers:
            runs = [("gui", "sdl and not network", {})]
            how = "headless"
        elif "offscreen" in drivers:
            runs = [("gui", "sdl and not network", {'PM_TEST_VIDEODRIVER': "offscreen"})]
            how = "headless (offscreen)"
        else:
            ## One display: tests that start their own pugwash run once the others have closed theirs.
            real = {'PM_TEST_VIDEODRIVER': ""}
            runs = [
                ("gui", "sdl and not own_display and not network", real),
                ("gui-own-display", "own_display and not network", real),
                ]
            how = "on the real screen"
            self.say("Running the GUI tests next, the screen will flicker for a while.")
            time.sleep(3)

        self.ui_stop()
        results = [self._pytest(name, marker, timeout=1500, extra_env=env, label="GUI tests") for name, marker, env in runs]
        set_from_results(section, results, suffix=f" ({how})")
        self.ui_start()

    def step_smoke(self, section):
        try:
            socket.create_connection(("github.com", 443), timeout=5).close()
        except OSError:
            section.set(SKIP, "skipped, no internet connection")
            return

        self.say(f"Installing and removing {SMOKE_PORT} from the internet.")
        out = self.work / "smoke"
        scratch = self.work / "scratch"
        ports = scratch / "ports"
        ports.mkdir(parents=True, exist_ok=True)

        ## The installed PortMaster and its cache, ports into a scratch folder, and the plain
        ## platform: CFW hooks (eg: muOS's catalogue) would write outside that folder.
        env = self.test_env(HM_PORTS_DIR=str(ports), HM_SCRIPTS_DIR=str(ports), CFW_NAME="default")
        harbourmaster = [sys.executable, self.controlfolder / "harbourmaster", "--no-check", "--no-colour"]

        steps = []
        for name, args, check in (
                ("install", ["install", SMOKE_PORT], lambda: (ports / SMOKE_SCRIPT).is_file()),
                ("ports", ["ports"], lambda: True),
                ("uninstall", ["uninstall", SMOKE_PORT], lambda: not (ports / SMOKE_SCRIPT).exists()),
                ("runtime_list", ["runtime_list"], lambda: True),
                ):
            code, text = self.run(harbourmaster + args, timeout=600, env=env, cwd=self.controlfolder, output=out / f"{name}.txt")
            ok = code == 0 and check() and "Traceback" not in text
            steps.append((name, ok, code))

        shutil.rmtree(str(scratch), ignore_errors=True)
        failed = [name for name, ok, code in steps if not ok]
        details = "\n".join(f"- {name}: {'ok' if ok else f'FAILED (exit {code})'}" for name, ok, code in steps)
        if failed:
            section.set(FAIL, "failed: " + ", ".join(failed), details)
        else:
            section.set(PASS, f"installed and removed {SMOKE_PORT}", details)

    def step_interactive(self, section):
        if not self.has_ui:
            section.set(SKIP, "skipped, no screen")
            return

        if not self.ui.message_box(
                "Last part: four quick button checks, one after the other. Read each question before pressing:\n\n"
                "1. the button the bottom bar shows next to OKAY\n"
                "2. the button the bottom bar shows next to CANCEL\n"
                "3. the button printed with A on your device\n"
                "4. the button printed with B on your device\n\n"
                "Press A to begin, or B to skip them.", want_cancel=True):
            section.set(SKIP, "skipped by the tester")
            return

        attempts = {}

        def ask(number, key, retry=False):
            _, name, prompt, _ = BUTTON_CHECKS[number]
            text = f"Button check {number + 1} of {len(BUTTON_CHECKS)}\n\n{prompt}"
            if retry:
                text = f"ARE YOU SURE YOU PRESSED {name.upper()}?!?!?!?!\n\nOnce more:\n\n{prompt}"

            attempts.setdefault(key, []).append(self.ui.message_box(text, want_cancel=True))

        for number, (key, _, _, expected) in enumerate(BUTTON_CHECKS):
            ask(number, key)
            if expected is not None and attempts[key][-1] is not expected:
                ask(number, key, retry=True)

        ## The physical pair has to differ, otherwise ask for both again.
        if attempts["physical_a"][-1] == attempts["physical_b"][-1]:
            ask(2, "physical_a", retry=True)
            ask(3, "physical_b", retry=True)

        problems, details = button_verdict(attempts)
        details.append(f"Answers (True = accepted): {attempts}")
        answers = dict(attempts)

        self.ui.messages_end()
        self.ui.messages_begin()

        portmsg = self.controlfolder / f"portmsg.{os.environ.get('DEVICE_ARCH', platform.machine())}"
        if os.access(str(portmsg), os.X_OK):
            self.ui_stop()
            env = self.test_env()
            if os.environ.get("SDL_GAMECONTROLLERCONFIG") is None and os.environ.get("sdl_controllerconfig"):
                env["SDL_GAMECONTROLLERCONFIG"] = os.environ["sdl_controllerconfig"]

            code, text = self.run(
                [portmsg, "--type", "info", "--timeout", "4", "--title", "PortMaster Test Suite",
                 "--text", "This message is drawn by portmsg. It closes by itself."],
                timeout=30, env=env, output=self.work / "interactive" / "portmsg.txt")
            self.ui_start()

            seen = self.ui.message_box(
                "Did you just see a message titled \"PortMaster Test Suite\"?", want_cancel=True, ok_text="Yes", cancel_text="No")
            answers['portmsg'] = seen
            if not seen:
                problems.append(f"the portmsg message wasn't seen (exit {code})")
        else:
            details.append("No portmsg for this architecture, pugwash shows pm_message instead.")

        (self.work / "interactive").mkdir(parents=True, exist_ok=True)
        (self.work / "interactive" / "answers.json").write_text(json.dumps(answers, indent=2))

        if problems:
            section.set(FAIL, "; ".join(problems), "\n".join(details))
        else:
            section.set(PASS, "buttons and messages work", "\n".join(details))

    ## The whole run.
    def main(self):
        skip = set(self.options.skip)
        self.log(f"PortMaster Test Suite, controlfolder {self.controlfolder}, work {self.work}, python {sys.executable}")

        self.ui_start()
        if self.has_ui and "install" not in skip:
            version = zipfile.ZipFile(str(PM_ZIP)).read("PortMaster/version").decode().strip()
            if not self.ui.message_box(
                    f"PortMaster Test Suite\n\nThis installs PortMaster {version} and tests it on this device. "
                    "It takes 5 to 15 minutes, and the screen will flicker during the GUI tests.\n\n"
                    "Press A to start, or B to quit.", want_cancel=True):
                self.log("cancelled by the tester")
                self.ui_stop()
                return 0

        for key in STEPS:
            section = self.section(key)
            if key in skip:
                section.set(SKIP, "skipped (--skip)")
                continue

            started = time.monotonic()
            try:
                getattr(self, f"step_{key}")(section)

            except Exception as err:
                self.log(f"{key}: crashed\n{traceback.format_exc()}")
                section.set(FAIL, f"the step crashed: {err}", traceback.format_exc(limit=5))

                if not self.has_ui and not self.options.no_ui:
                    self.ui_start()

            section.seconds = time.monotonic() - started
            self.log(f"{key}: {section.status} - {section.summary}")

        name = report_name(self.info, self.started)
        report = write_report(REPORTS / name, self.work, self.sections, self.info, extra_files=[
            (self.controlfolder / "pugwash.txt", "portmaster/pugwash.txt"),
            (self.controlfolder / "harbourmaster.txt", "portmaster/harbourmaster.txt"),
            (self.controlfolder / "log.txt", "portmaster/log.txt"),
            ])
        self.log(f"report: {report}")

        if self.has_ui:
            self.ui.messages_end()
            self.ui.selection_list("pmtest", summary_entries(self.sections, name))

        self.ui_stop()
        print(summary_text(self.sections, self.info))
        return 1 if any(section.status == FAIL for section in self.sections) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="PortMaster Test Suite")
    parser.add_argument("--no-ui", action="store_true", help="don't use the screen (pugwash)")
    parser.add_argument("--skip", default="", help="comma separated steps to skip: " + ",".join(STEPS))
    parser.add_argument("--controlfolder", default=None)
    options = parser.parse_args(argv)
    options.skip = [step for step in options.skip.split(",") if step]

    return Suite(options).main()


if __name__ == '__main__':
    sys.exit(main())
