# SPDX-License-Identifier: MIT
#
# The PortMaster Test Suite port (tools/test_suite): its results, summary and report,
# and its fifo client driving a real pugwash.

import io
import json
import os
import re
import shutil
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from conftest import PM_DIR, REPO_DIR, basic_port_files, write_port_zip


sys.path.insert(0, str(REPO_DIR / "tools" / "test_suite" / "pmtest"))
import suite  # noqa: E402
from fifo import Dialog  # noqa: E402


JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="5">
  <testcase classname="tests.test_a" name="test_ok" time="0.1"/>
  <testcase classname="tests.test_a" name="test_ok_too" time="0.1"/>
  <testcase classname="tests.test_b" name="test_broken" time="0.2">
    <failure message="AssertionError: assert 1 == 2">long traceback</failure>
  </testcase>
  <testcase classname="tests.test_c" name="test_gui" time="0.0">
    <skipped type="pytest.skip" message="SDL video driver 'dummy' unavailable"/>
  </testcase>
  <testcase classname="tests.test_c" name="test_gui_2" time="0.0">
    <skipped type="pytest.skip" message="SDL video driver 'dummy' unavailable"/>
  </testcase>
</testsuite></testsuites>
"""


def test_parse_junit(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT)

    result = suite.parse_junit(junit)

    assert (result['tests'], result['passed'], result['failed'], result['errors'], result['skipped']) == (5, 2, 1, 0, 2)
    assert result['failures'] == [("tests.test_b::test_broken", "AssertionError: assert 1 == 2")]
    assert result['skip_reasons'] == {"SDL video driver 'dummy' unavailable": 2}

    text, details = suite.junit_summary(result)
    assert text == "2 passed, 1 failed, 2 skipped"
    assert "- tests.test_b::test_broken: AssertionError: assert 1 == 2" in details
    assert "- 2 x SDL video driver 'dummy' unavailable" in details


def test_set_from_results():
    ok = {'tests': 2, 'passed': 2, 'failed': 0, 'errors': 0, 'skipped': 0, 'failures': [], 'skip_reasons': {}}
    broken = {'tests': 1, 'passed': 0, 'failed': 1, 'errors': 0, 'skipped': 0,
              'failures': [("tests.t::test_x", "boom")], 'skip_reasons': {}}
    skipped = {'tests': 3, 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 3, 'failures': [], 'skip_reasons': {"no SDL": 3}}

    section = suite.Section("gui", "GUI tests")
    suite.set_from_results(section, [ok, ok], suffix=" (on the real screen)")
    assert (section.status, section.summary) == (suite.PASS, "4 passed, 0 failed, 0 skipped (on the real screen)")

    suite.set_from_results(section, [ok, broken])
    assert section.status == suite.FAIL
    assert "tests.t::test_x: boom" in section.details

    suite.set_from_results(section, [skipped])
    assert section.status == suite.SKIP
    assert "3 x no SDL" in section.details

    ## A run that never finished is a failure, with why.
    suite.set_from_results(section, [ok, {'error': "pytest didn't finish (exit -9)"}])
    assert section.status == suite.FAIL
    assert "exit -9" in section.details


def sections(*states):
    result = []
    for number, (status, summary) in enumerate(states):
        section = suite.Section(f"s{number}", f"Section {number}")
        section.set(status, summary, "some details" if status == suite.FAIL else "")
        result.append(section)

    return result


def test_summary_entries_all_passed():
    entries = suite.summary_entries(
        sections((suite.PASS, "fine"), (suite.INFO, "info"), (suite.SKIP, "offline")), "knulli-rg-20261013-2000.zip")

    assert entries[0][:2] == ("#overall", "All 1 checks passed")
    assert [title for _, title, _ in entries[1:-1]] == ["PASS: Section 0", "INFO: Section 1", "SKIP: Section 2"]
    assert entries[-1][0] == "#report"
    assert "knulli-rg-20261013-2000.zip" in entries[-1][2]


def test_summary_entries_with_a_failure():
    entries = suite.summary_entries(sections((suite.PASS, "fine"), (suite.FAIL, "3 failed")), "r.zip")

    assert entries[0][1] == "1 of 2 checks failed"
    assert "Section 1" in entries[0][2]
    ## Selecting a section shows its details.
    assert entries[2][2] == "3 failed\n\nsome details"


def test_report_name():
    when = suite.datetime.datetime(2026, 10, 13, 20, 5)
    assert suite.report_name({'cfw': "muOS", 'device': "TrimUI Brick Pro"}, when) == "muOS-TrimUI_Brick_Pro-20261013-2005.zip"
    assert suite.report_name({}, when) == "cfw-device-20261013-2005.zip"


def test_write_report(tmp_path):
    work = tmp_path / "work"
    (work / "pytest").mkdir(parents=True)
    (work / "pytest" / "junit.xml").write_text(JUNIT)
    (work / "run.log").write_text("log")
    (work / "progress").write_text("1 2")
    (work / "scratch" / "ports").mkdir(parents=True)
    (work / "scratch" / "ports" / "big.bin").write_text("not in the report")
    pugwash_log = tmp_path / "pugwash.txt"
    pugwash_log.write_text("pugwash log")

    report = suite.write_report(
        tmp_path / "reports" / "r.zip", work, sections((suite.PASS, "fine")), {'cfw': "test"},
        extra_files=[(pugwash_log, "portmaster/pugwash.txt"), (tmp_path / "missing.txt", "portmaster/missing.txt")])

    with zipfile.ZipFile(report) as zf:
        assert sorted(zf.namelist()) == ["portmaster/pugwash.txt", "pytest/junit.xml", "run.log", "summary.json", "summary.txt"]
        data = json.loads(zf.read("summary.json"))

    assert data['info'] == {'cfw': "test"}
    assert data['sections'][0]['status'] == "pass"


@pytest.mark.parametrize("line, scrubbed", [
    ## From real reports.
    ("[   12.5] wlan0: authenticate with 0c:c6:55:66:7b:3d", "[   12.5] wlan0: authenticate with xx:xx:xx:xx:xx:xx"),
    ("Bluetooth: hci0: BD_ADDR 00-03-7F-95-00-45 set", "Bluetooth: hci0: BD_ADDR xx:xx:xx:xx:xx:xx set"),
    ("RTW: set pairwise key camid:0, addr:9e:86:dd:d7:b6:d9, kid:0", "RTW: set pairwise key camid:0, addr:xx:xx:xx:xx:xx:xx, kid:0"),
    ("cfg80211_rtw_change_station(wlan0) mac:9e:86:dd:d7:b6:d9", "cfg80211_rtw_change_station(wlan0) mac:xx:xx:xx:xx:xx:xx"),
    ("SERIAL=MQ66142507031604", "SERIAL=xxxx"),
    ("usb 1-1: SerialNumber: 0123456789AB", "usb 1-1: SerialNumber: xxxx"),
    ("got 192.168.68.138 from dhcp, gateway 10.0.0.1", "got x.x.x.138 from dhcp, gateway x.x.x.1"),
    ("inet6 fe80::1a2b:3c4d:5e6f:7a8b/64", "inet6 x::x/64"),
    ("wlan0: connected to SSID=\"Home Network\"", "wlan0: connected to SSID=xxxx"),
    ("ESSID:MyWifi", "ESSID:xxxx"),
    ## Not addresses: versions, times, loopback, public addresses.
    ("runtime godot 6.12.0.122 and 3.5.2", "runtime godot 6.12.0.122 and 3.5.2"),
    ("14:10:18 started, 0:0:0:1 scsi", "14:10:18 started, 0:0:0:1 scsi"),
    ("listening on 127.0.0.1 and ::1", "listening on 127.0.0.1 and ::1"),
    ("github.com is 140.82.112.3", "github.com is 140.82.112.3"),
    ("serial-getty@ttyFIQ0.service, serializers_osgga.so", "serial-getty@ttyFIQ0.service, serializers_osgga.so"),
    ("as /devices/platform/soc@0/888000.serial/888000.serial:0/input", "as /devices/platform/soc@0/888000.serial/888000.serial:0/input"),
    ("tests.test_hardware::test_device_info_defaults: assert", "tests.test_hardware::test_device_info_defaults: assert"),
    ])
def test_scrub(line, scrubbed):
    assert suite.scrub(line) == scrubbed


def test_scrub_hostname():
    assert suite.scrub("ark353v login: ark353v-ish ark353v", ["ark353v"]) == "device-host login: ark353v-ish device-host"

    ## Only when it isn't just the device's (or CPU's) name, those are in every report anyway.
    assert suite.private_names("muos-6b1c52", {'device': "rg35xx-h"}) == ["muos-6b1c52"]
    assert suite.private_names("RG351MP", {'device': "RG351MP"}) == []
    assert suite.private_names("SM6115", {'device': "MANGMI Air X MQ66"}, cpu="sm6115") == []
    assert suite.private_names("knulli", {}) == []
    assert suite.private_names("gladiator", {'cfw_version': "gladiator"}) == []
    assert suite.private_names("", {}) == []


def test_write_report_scrubs(tmp_path):
    work = tmp_path / "work"
    (work / "device").mkdir(parents=True)
    (work / "device" / "dmesg.txt").write_text("wlan0: 68:8f:c9:0e:98:a9 on mydevice at 192.168.1.20\n")
    (work / "binary.bin").write_bytes(b"\xff\xfe 192.168.1.20")
    log = tmp_path / "pugwash.txt"
    log.write_text("mydevice: fetched from 192.168.1.20\n")

    report = suite.write_report(
        tmp_path / "r.zip", work, sections((suite.PASS, "fine")), {'cfw': "test"},
        extra_files=[(log, "portmaster/pugwash.txt")], names=["mydevice"])

    with zipfile.ZipFile(report) as zf:
        assert zf.read("device/dmesg.txt").decode() == "wlan0: xx:xx:xx:xx:xx:xx on device-host at x.x.x.20\n"
        assert zf.read("portmaster/pugwash.txt").decode() == "device-host: fetched from x.x.x.20\n"
        ## Not text: as it was.
        assert zf.read("binary.bin") == b"\xff\xfe 192.168.1.20"
        assert json.loads(zf.read("summary.json"))['scrubbed'] is True


@pytest.mark.parametrize("text, name", [
    ('NAME=Buildroot\nPRETTY_NAME="Buildroot 2021.11"\n', "Buildroot 2021.11"),
    ('PRETTY_NAME=\\"Batocera.linux gladiator\\"\n', "Batocera.linux gladiator"),
    ("NAME=x\n", ""),
    ])
def test_os_release_name(tmp_path, text, name):
    (tmp_path / "os-release").write_text(text)
    assert suite.os_release_name(tmp_path / "os-release") == name
    assert suite.os_release_name(tmp_path / "missing") == ""


def test_pick_work_dir(tmp_path, monkeypatch):
    first, second = tmp_path / "tmpfs", tmp_path / "sdcard"

    assert suite.pick_work_dir([first, second], need_bytes=1) == first

    ## Not enough room anywhere: the first that can hold a fifo.
    assert suite.pick_work_dir([first, second], need_bytes=1 << 62) == first
    assert not list(first.iterdir())


def test_pick_work_dir_no_fifo(tmp_path, monkeypatch):
    ## The suite on a FAT card with a small /tmp (CubeXX on spruce): /tmp, not the card.
    small, sdcard = tmp_path / "tmpfs", tmp_path / "sdcard"
    real_mkfifo = os.mkfifo

    def mkfifo(path, *args, **kwargs):
        if Path(path).parent == sdcard:
            raise PermissionError(1, "Operation not permitted")

        return real_mkfifo(path, *args, **kwargs)

    monkeypatch.setattr(suite.os, "mkfifo", mkfifo)
    small.mkdir()
    sdcard.mkdir()
    assert not suite.holds_fifo(sdcard)
    assert suite.holds_fifo(small)

    assert suite.pick_work_dir([sdcard, small], need_bytes=1) == small
    assert suite.pick_work_dir([small, sdcard], need_bytes=1 << 62) == small

    ## Nowhere can: the last one, as before.
    def no_mkfifo(path, *args, **kwargs):
        raise OSError("no fifos here")

    monkeypatch.setattr(suite.os, "mkfifo", no_mkfifo)
    assert suite.pick_work_dir([small, sdcard], need_bytes=1) == sdcard


@pytest.mark.parametrize("stub, hooks", [
    ("PortMaster.sh", ""),
    ("spruce/PortMaster.txt", "spruce"),
    ("muos/PortMaster.txt", "muos"),
    ])
def test_launcher_hooks(tmp_path, stub, hooks):
    pm = tmp_path / "PortMaster"
    pm.mkdir()
    shutil.copy(str(PM_DIR / stub), str(pm / "PortMaster.sh"))

    assert suite.launcher_hooks(pm) == hooks


def test_launcher_hooks_trimui(tmp_path):
    ## TrimUI's stub is launch.sh next to the PortMaster folder.
    (tmp_path / "PortMaster").mkdir()
    shutil.copy(str(PM_DIR / "trimui" / "PortMaster.txt"), str(tmp_path / "launch.sh"))

    assert suite.launcher_hooks(tmp_path / "PortMaster") == "trimui"


def fake_controlfolder(tmp_path, cfw=None):
    pm = tmp_path / "PortMaster"
    (pm / "utils").mkdir(parents=True)
    shutil.copy(str(PM_DIR / "utils" / "pm_launch.txt"), str(pm / "utils" / "pm_launch.txt"))
    shutil.copy(str(PM_DIR / ((cfw + "/PortMaster.txt") if cfw else "PortMaster.sh")), str(pm / "PortMaster.sh"))
    if cfw:
        (pm / cfw).mkdir()
        shutil.copy(str(PM_DIR / cfw / "launch_hooks.txt"), str(pm / cfw / "launch_hooks.txt"))

    control = 'CFW_NAME="Test"\nESUDO=""\nexport PMTEST_FAKE="from control.txt"\nget_controls() { :; }\n'
    (pm / "control.txt").write_text(control)
    (pm / "device_info.txt").write_text(control)
    pugwash = pm / "pugwash"
    pugwash.write_text("#!/bin/sh\ntouch ran-pugwash\n")
    pugwash.chmod(0o755)
    return pm


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_launcher_env(tmp_path, monkeypatch):
    monkeypatch.delenv("PYSDL2_DLL_PATH", raising=False)
    pm = fake_controlfolder(tmp_path)

    env = suite.launcher_env(pm)

    assert env['PYSDL2_DLL_PATH'] == "/usr/lib"
    assert env['PMTEST_FAKE'] == "from control.txt"
    assert "PM_LAUNCH_ENV_ONLY" not in env
    ## Nothing launched.
    assert not (pm / "ran-pugwash").exists()
    assert not (pm / "log.txt").exists()


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_launcher_env_trimui(tmp_path):
    env = suite.launcher_env(fake_controlfolder(tmp_path, "trimui"))
    assert env['PYSDL2_DLL_PATH'] == "/usr/trimui/lib"


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_launcher_env_rocknix(tmp_path, monkeypatch):
    ## ROCKNIX's control.txt sets no CFW_NAME, so mod_.txt runs device_info.txt. The port
    ## script already ran the old one; its CFW_NAME mustn't skip the new one.
    pm = fake_controlfolder(tmp_path)
    (pm / "control.txt").write_text('ESUDO=""\nget_controls() { :; }\n')
    (pm / "mod_.txt").write_text('source "$controlfolder/device_info.txt"\n')
    (pm / "device_info.txt").write_text('export CFW_NAME="ROCKNIX"\nexport DEVICE_INFO_VERSION="new"\n')
    for key, value in (("CFW_NAME", "ROCKNIX"), ("DEVICE_INFO_VERSION", "old"), ("DISPLAY_WIDTH", "1"), ("PM_VERSION", "old")):
        monkeypatch.setenv(key, value)

    env = suite.launcher_env(pm)

    assert env['DEVICE_INFO_VERSION'] == "new"
    assert "DISPLAY_WIDTH" not in env and "PM_VERSION" not in env


def test_launcher_env_old_portmaster(tmp_path):
    ## A PortMaster from before PM_LAUNCH_ENV_ONLY would run the whole launcher: not asked.
    pm = fake_controlfolder(tmp_path)
    launch = pm / "utils" / "pm_launch.txt"
    launch.write_text(launch.read_text().replace("PM_LAUNCH_ENV_ONLY", "PM_SOMETHING_ELSE"))

    assert suite.launcher_env(pm) is None
    assert suite.launcher_env(tmp_path / "nowhere") is None


def test_port_zip_layout():
    ## What do_release.sh packs (tested end to end in test_build.py).
    port_json = json.loads((REPO_DIR / "tools" / "test_suite" / "pmtest" / "port.json").read_text())
    assert port_json['name'] == "pmtest.zip"
    assert port_json['items'] == ["PortMaster Test Suite.sh", "pmtest/"]
    assert (REPO_DIR / "tools" / "test_suite" / "PortMaster Test Suite.sh").is_file()


################################################################################
## The fifo client against a real pugwash.
@pytest.mark.sdl
@pytest.mark.own_display
def test_dialog_drives_pugwash(hm_dirs, tmp_path):
    env = dict(os.environ)
    env.update({
        'HM_TOOLS_DIR': str(hm_dirs['tools_dir']),
        'HM_PORTS_DIR': str(hm_dirs['ports_dir']),
        'HM_SCRIPTS_DIR': str(hm_dirs['scripts_dir']),
        })

    dialog = Dialog(PM_DIR, tmp_path / "fifo", env=env)
    try:
        assert dialog.start("--offline", "--no-check", "--no-log")
        assert dialog.messages_begin() == "DONE"
        assert dialog.message("Line one\nline two") == "DONE"
        assert dialog.progress("Testing (1/2)", 1, 2) == "DONE"
        assert dialog.progress_clear() == "DONE"

        zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())
        assert dialog.install(zip_file) is True
        assert (hm_dirs['ports_dir'] / "Test Port.sh").is_file()

        assert dialog.messages_end() == "DONE"

    finally:
        dialog.stop()

    assert not dialog.running
    ## Gone: commands answer None instead of hanging.
    assert dialog.message("anyone there?") is None


def test_dialog_without_pugwash(tmp_path):
    dialog = Dialog(tmp_path / "nowhere", tmp_path / "fifo")

    assert dialog.start(timeout=5) is False
    assert dialog.message_box("hello", want_cancel=True) is None
    assert dialog.install(tmp_path / "x.zip") is None


@pytest.mark.parametrize("attempts, problems, notes", [
    ## All right first time.
    ({'labelled_ok': [True], 'labelled_cancel': [False], 'physical_a': [True], 'physical_b': [False]},
     [], ["The physical A button accepts."]),
    ## A swapped device: B accepts. Not a problem, it's what the device does.
    ({'labelled_ok': [True], 'labelled_cancel': [False], 'physical_a': [False], 'physical_b': [True]},
     [], ["The physical B button accepts."]),
    ## A slip, then right on the retry: passes, and says so.
    ({'labelled_ok': [False, True], 'labelled_cancel': [False], 'physical_a': [True], 'physical_b': [False]},
     [], ["the OKAY button: right on the second try", "The physical A button accepts."]),
    ## Wrong twice: a real problem.
    ({'labelled_ok': [True], 'labelled_cancel': [True, True], 'physical_a': [True], 'physical_b': [False]},
     ["the CANCEL button did not cancel"], ["The physical A button accepts."]),
    ## A and B did the same, then differed on the retry.
    ({'labelled_ok': [True], 'labelled_cancel': [False], 'physical_a': [True, True], 'physical_b': [True, False]},
     [], ["The physical A button accepts.", "A / B: right on the second try"]),
    ## A and B still the same.
    ({'labelled_ok': [True], 'labelled_cancel': [False], 'physical_a': [True, True], 'physical_b': [True, True]},
     ["the A and B buttons did the same thing"], []),
    ])
def test_button_verdict(attempts, problems, notes):
    assert suite.button_verdict(attempts) == (problems, notes)


################################################################################
## tools/test_suite/matrix.py: the coverage matrix from a folder of reports.
sys.path.insert(0, str(REPO_DIR / "tools" / "test_suite"))
import devices  # noqa: E402
import matrix  # noqa: E402
import receive  # noqa: E402


def make_report(folder, name, info, states, environment=None, os_release=None, cfw_files=None):
    work = folder / ("work-" + name)
    work.mkdir(parents=True)
    (work / "device").mkdir()
    if environment is not None:
        (work / "device" / "environment.txt").write_text(environment)
    if os_release is not None:
        (work / "device" / "os-release.txt").write_text(os_release)
    if cfw_files is not None:
        (work / "device" / "cfw-version.txt").write_text(cfw_files)

    report_sections = []
    for key, status, summary, details in states:
        section = suite.Section(key, key.title())
        section.set(status, summary, details)
        report_sections.append(section)

    return suite.write_report(folder / name, work, report_sections, info)


def test_matrix(tmp_path):
    reports = tmp_path / "reports"
    base = {'cfw': "muOS", 'cfw_version': "2601.0_JACARANDA", 'device': "rg35xx-h", 'arch': "aarch64",
            'python': "3.11.8", 'sdl': "SDL 2 28 5", 'portmaster': "2026-10-13_0969", 'video_drivers': ["mali"]}
    failed = "Failed:\n- tests.test_a::test_x: assert 1 == 2\nSkipped:\n- 2 x no shellcheck"

    make_report(reports, "old.zip", dict(base, started="2026-10-13T10:00:00"), [
        ("install", suite.PASS, "installed", ""),
        ("pytest", suite.FAIL, "1 passed, 1 failed, 2 skipped", failed)])
    make_report(reports, "new.zip", dict(base, started="2026-10-13T12:00:00"), [
        ("install", suite.PASS, "installed", ""),
        ("gui", suite.PASS, "120 passed, 0 failed, 0 skipped (on the real screen)", "")])
    make_report(reports, "knulli.zip", dict(base, cfw="knulli", cfw_version="scarab", device="<rg-cubexx>", started="2026-10-13T11:00:00"), [
        ("pytest", suite.FAIL, "1 passed, 1 failed, 2 skipped", failed),
        ("gui", suite.PASS, "120 passed, 0 failed, 0 skipped (headless (offscreen))", "")])
    ## Not reports: skipped.
    (reports / "junk.zip").write_bytes(b"not a zip")
    with zipfile.ZipFile(reports / "other.zip", "w") as zf:
        zf.writestr("readme.txt", "hello")

    rows = matrix.read_reports(reports)
    assert [row['report'] for row in rows] == ["new.zip", "knulli.zip", "old.zip"]
    assert rows[0]['gui_how'] == "real screen" and rows[1]['gui_how'] == "headless"
    assert rows[0]['ok'] and not rows[2]['ok']
    assert rows[2]['failures'] == [{'section': "pytest", 'test': "tests.test_a::test_x", 'message': "assert 1 == 2"}]
    assert rows[0]['scrubbed'] is True

    groups = matrix.group_rows(rows)
    assert list(groups) == [("knulli", "scarab", "<rg-cubexx>"), ("muOS", "2601.0 Jacaranda", "rg35xx-h")]
    ## Newest run first.
    assert [row['report'] for row in groups[("muOS", "2601.0 Jacaranda", "rg35xx-h")]] == ["new.zip", "old.zip"]

    (test, message, found), = matrix.failure_index(rows)
    assert (test, message, len(found)) == ("tests.test_a::test_x", "assert 1 == 2", 2)

    page = matrix.render_html(rows)
    assert page.startswith("<title>PortMaster Test Matrix</title>")
    assert "Test build <span class=\"data\">2026-10-13_0969</span>." in page
    assert "&lt;rg-cubexx&gt;" in page and "<rg-cubexx>" not in page
    assert "<script" not in page

    assert matrix.main([str(reports), "--out", str(tmp_path / "out")]) == 0
    assert len(json.loads((tmp_path / "out" / "matrix.json").read_text())) == 3
    assert (tmp_path / "out" / "matrix.html").is_file()


@pytest.mark.parametrize("cfw, version, os_release, expected", [
    ("ROCKNIX", "20260925", 'BUILD_DATE="Fri Sep 25 09:06:26 UTC 2026"\n', "2026-09-25"),
    ("AmberELEC", "prerelease-20261003_1121", "", "2026-10-03"),
    ("dArkOS", "05102026", "", "2026-05-10"),
    ("dArkOS", "01302026", "", "2026-01-30"),
    ("ArkOS", "08242025", "", "2025-08-24"),
    ("muOS", "2601.0_JACARANDA", "VERSION_ID=2601.0\n", "2026-01"),
    ("muOS", "2410", "", "2024-10"),
    ("knulli", "42", "VERSION=42\nVERSION_ID=2024.11\nOS_DATE=20251128\n", "2025-11-28"),
    ("AmberELEC", "20211122", 'BUILD_DATE="Sat Oct  3 11:36:04 UTC 2026"\n', "2021-11-22"),
    ("spruce", "4.5.5", "VERSION_ID=2021.11\n", ""),
    ("spruce", "2021.11", "", ""),
    ("RetroDECK", "0.10.0b", 'VERSION_ID="6.10"\n', ""),
    ])
def test_matrix_release_date(cfw, version, os_release, expected):
    assert matrix.release_date(cfw, version, os_release) == expected


@pytest.mark.parametrize("version, os_name, expected", [
    ("2601.0_JACARANDA", "MustardOS 2601.0 (JACARANDA)", "2601.0 Jacaranda"),
    ("2606.0_ANDROMEDA", "MustardOS 2606.0 (ANDROMEDA)", "2606.0 Andromeda"),
    ("2601.1_FUNKY_JACARANDA", "", "2601.1 Funky Jacaranda"),
    ("2410", "muOS 2410 Banana", "2410 Banana"),
    ("2410", "", "2410 Banana"),
    ("2508", "", "2508 Goose"),
    ("9999.0", "", "9999.0"),
    ])
def test_matrix_muos_release(version, os_name, expected):
    assert matrix.muos_release(version, os_name) == expected
    if expected[:4] in ("2601", "2410"):
        assert matrix.release_date("muOS", expected, "") == f"20{expected[:2]}-{expected[2:4]}"


def test_matrix_groups_date_versions_by_month(tmp_path):
    ## ArkOS 02012025-3 and 02012025 are separate releases, one heading for February 2025.
    base = {'arch': "aarch64", 'python': "3.7.5", 'sdl': "SDL 2 26 2", 'portmaster': "2026-10-15_0669", 'cfw': "ArkOS"}
    passed = [("install", suite.PASS, "installed", "")]
    make_report(tmp_path, "a.zip", dict(base, cfw_version="02012025-3", device="RG353M", started="2026-10-15T01:00:00"), passed)
    make_report(tmp_path, "b.zip", dict(base, cfw_version="02012025", device="RG353V", started="2026-10-15T02:00:00"), passed)
    make_report(tmp_path, "c.zip", dict(base, cfw_version="01152023-1", device="RG351MP", started="2026-10-15T03:00:00"), passed)

    rows = matrix.read_reports(tmp_path)
    assert [key[1] for key in matrix.group_rows(rows)] == ["2025-02", "2025-02", "2023-01"]

    page = matrix.render_html(rows)
    assert "2025-02 <span class=muted>02012025-3, 02012025</span>" in page
    assert "aarch64 · 02012025-3</span>" in page and "aarch64 · 01152023-1</span>" in page


@pytest.mark.parametrize("built, expected", [
    ("2026-08-19", ("scarab", "2026-05-11")),        ## Brick Pro: "scarab 2026/08/19"
    ("2026-05-11", ("scarab", "2026-05-11")),
    ("2026-10-12", ("scarab", "2026-05-11")),        ## Batocera 44-dev builds
    ("2025-11-28", ("gladiator II", "2025-08-13")),  ## Smart Pro: "alpha 2025/11/28"
    ("2025-05-05", ("gladiator", "2025-05-05")),
    ("2024-07-30", ("20240721", "2024-07-21")),
    ("2024-01-01", ("", "")),
    ("", ("", "")),
    ])
def test_matrix_knulli_release(built, expected):
    assert matrix.knulli_release(built) == expected


def test_matrix_by_cfw_then_version(tmp_path):
    ## CFW, then its versions newest release first (version number when there's no date,
    ## Unknown last), then devices.
    base = {'arch': "aarch64", 'python': "3.11.8", 'sdl': "SDL 2 28 5", 'portmaster': "2026-10-15_0369"}
    passed = [("install", suite.PASS, "installed", "")]
    passed_with_device = passed + [("device", suite.INFO, "knulli 42 on trimui-brick-pro (aarch64), Python 3.12.8", "")]
    for name, info, os_release in (
            ("rocknix-old.zip", dict(cfw="ROCKNIX", cfw_version="20250517", device="rp5"), ""),
            ("rocknix-new.zip", dict(cfw="ROCKNIX", cfw_version="20261010", device="rp5"), ""),
            ("knulli-old.zip", dict(cfw="knulli", cfw_version="scarab", device="rg-cubexx"), "VERSION=gladiator\nOS_DATE=20250506\n"),
            ("knulli-tsp.zip", dict(cfw="knulli", cfw_version="42", device="trimui-smart-pro", os="Batocera.linux 42"), "VERSION=42\nOS_DATE=20251128\n"),
            ("knulli-brick.zip", dict(cfw="knulli", cfw_version="42", device="trimui-brick-pro"), "VERSION=42\nOS_DATE=20260819\n"),
            ("knulli-cube.zip", dict(cfw="knulli", cfw_version="42", device="rgcubexx-h"), "VERSION=42\nOS_DATE=20260511\n"),
            ("spruce-new.zip", dict(cfw="spruce", cfw_version="4.5.5", device="Miyoo Flip"), ""),
            ("spruce-old.zip", dict(cfw="spruce", cfw_version="2022.05", device="sun55iw3"), ""),
            ("retrodeck-a.zip", dict(cfw="RetroDECK", cfw_version="0.10.0b", device="Steam Deck"), ""),
            ("retrodeck-b.zip", dict(cfw="RetroDECK", cfw_version="0.10.10b", device="Steam Deck"), ""),
            ):
        make_report(tmp_path, name, dict(base, started="2026-10-15T01:00:00", **info), passed, os_release=os_release)

    rows = matrix.read_reports(tmp_path)
    versions = []
    for cfw, version, _ in matrix.group_rows(rows):
        if (cfw, version) not in versions:
            versions.append((cfw, version))

    assert versions == [
        ("knulli", "scarab"), ("knulli", "gladiator II"), ("knulli", "gladiator"),
        ("RetroDECK", "0.10.10b"), ("RetroDECK", "0.10.0b"),
        ("ROCKNIX", "2026-10"), ("ROCKNIX", "2025-05"),
        ("spruce", "4.5.5"), ("spruce", "Unknown")]

    ## (No catalogue: the grid would list Batocera as a CFW with devices but no reports.)
    page = matrix.render_html(rows, catalogue=[])
    assert "released 2026-05-11" in page and "released 2025-08-13" in page and "Batocera" not in page

    ## knulli's own version file beats os-release: the Brick Pro is scarab, on Batocera 42.
    make_report(tmp_path, "knulli-scarab.zip", dict(base, cfw="knulli", cfw_version="42", device="trimui-brick-pro", started="2026-10-15T02:00:00"),
                passed, os_release="VERSION=42\nOS_DATE=20260819\n", cfw_files="/usr/share/knulli/knulli.version: scarab 2026/08/19 16:06\n")
    row = matrix.read_report(tmp_path / "knulli-scarab.zip")
    assert (row['cfw_version'], row['released']) == ("scarab", "2026-05-11")

    ## The device line in "Every run" says the corrected version too.
    make_report(tmp_path, "knulli-device.zip", dict(base, cfw="knulli", cfw_version="42", device="trimui-brick-pro", started="2026-10-15T02:00:00"),
                passed_with_device, os_release="VERSION=42\nOS_DATE=20260819\n")
    row = matrix.read_report(tmp_path / "knulli-device.zip")
    assert row['sections']['device']['summary'] == "knulli scarab (reported as 42) on trimui-brick-pro (aarch64), Python 3.12.8"

    rows[0]['portmaster'], rows[1]['portmaster'] = "2026-10-13_0469", "2026-10-15_0569"
    assert ' 3 test builds, <span class="data">2026-10-13_0469</span> to <span class="data">2026-10-15_0569</span>.' in matrix.render_html(rows)
    assert "released 2025-05-05" in page and "alpha" not in page and ">42<" not in page


def test_matrix_skips_oversized_summaries(tmp_path, monkeypatch):
    monkeypatch.setattr(matrix, "MAX_SUMMARY_BYTES", 10)
    make_report(tmp_path, "r.zip", {'cfw': "x"}, [("install", suite.PASS, "installed", "")])

    assert matrix.read_report(tmp_path / "r.zip") is None


@pytest.mark.parametrize("row, expected", [
    ({'device': "rg-cubexx"}, "Anbernic RG CubeXX"),
    ({'device': "RGCUBEXX-H"}, "Anbernic RG CubeXX"),
    ({'device': "Anbernic RG CubeXX", 'platform': "AnbernicRGCubeXX"}, "Anbernic RG CubeXX"),
    ({'device': "tui-brick-pro"}, "TrimUI Brick Pro"),
    ({'device': "trimui-brick-pro"}, "TrimUI Brick Pro"),
    ({'device': "TrimUI Brick Pro", 'platform': "BrickPro"}, "TrimUI Brick Pro"),
    ({'device': "TrimUI Brick"}, "TrimUI Brick"),
    ({'device': "tui-spoon"}, "TrimUI Smart Pro"),
    ({'device': "trimui-smart-pro-s"}, "TrimUI Smart Pro S"),
    ## spruce builds that only knew the SoC: its platform name, else the SoC and screen.
    ({'device': "sun55iw3", 'platform': "SmartProS"}, "TrimUI Smart Pro S"),
    ({'device': "sun55iw3", 'display': "1280x720"}, "TrimUI Smart Pro S"),
    ({'device': "sun50iw10", 'display': "1024x768"}, "TrimUI Brick"),
    ({'device': "sun50iw10", 'display': "640x480"}, "MagicX Zero 28"),
    ({'device': "MIYOO RK3566 355 V10 Board"}, "Miyoo Flip"),
    ({'device': "MLP1"}, "Miniloong Pocket 1"),
    ({'device': "MINILOONG"}, "Miniloong Pocket 1"),
    ({'device': "UDT R36UltraX"}, "R36 Ultra X"),
    ({'device': "Game Console R36Ultra X"}, "R36 Ultra X"),
    ({'device': "Game Console R36S"}, "R36S"),
    ({'device': "RK-G350-V"}, "Batlexp G350"),
    ({'device': "Powkiddy x55"}, "Powkiddy X55"),
    ({'device': "x55"}, "Powkiddy X55"),
    ({'device': "Steam Deck OLED"}, "Steam Deck"),
    ({'device': "RG40XX-V"}, "Anbernic RG40XX V"),
    ({'device': "rg35xx-h"}, "Anbernic RG35XX H"),
    ({'device': "Retroid Pocket 5"}, "Retroid Pocket 5"),
    ({'device': "MANGMI Air X MQ66"}, "MANGMI Air X"),
    ])
def test_devices_identify(row, expected):
    assert devices.identify(row).name == expected


def test_devices_unknown():
    assert devices.identify({'device': "Some New Handheld"}) is None
    assert devices.identify({'device': "sun50iw10", 'display': "800x600"}) is None


def test_devices_catalogue_from_device_info():
    ## The vendored PortMaster-Info list: every model is in the catalogue, its CFWs as reports spell them.
    device_info = devices.load_device_info()
    assert len(device_info) >= 40
    catalogue = devices.build_catalogue(device_info)
    assert all(cfw.lower() in devices.CFW_NAMES for cfws in device_info.values() for cfw in cfws)
    for model, cfws in device_info.items():
        for info in cfws.values():
            assert devices.identify({'device': info['device']}, catalogue) is not None, model

    by_name = {device.name: device for device in catalogue}
    assert set(by_name["Anbernic RG353V"].supported) == {"ArkOS"}
    assert set(by_name["Anbernic RG351P/M"].supported) >= {"AmberELEC", "ArkOS wuMMLe", "ROCKNIX"}
    ## Variants stay apart ("rg353m" doesn't name the RG353V), families group them.
    assert devices.identify({'device': "rg353m"}, catalogue).name == "Anbernic RG353M"
    assert by_name["Anbernic RG353V"].family == by_name["Anbernic RG ARC-D"].family
    assert by_name["TrimUI Brick"].family == by_name["TrimUI Smart Pro"].family != by_name["TrimUI Smart Pro S"].family
    assert {name for _, names in devices.FAMILIES for name in names} <= set(by_name)


@pytest.mark.parametrize("cfw, version, released, expected", [
    ("muOS", "2601.0 Jacaranda", "2026-01", "Jacaranda"),
    ("muOS", "2601.1 Funky Jacaranda", "2026-01", "Jacaranda"),
    ("muOS", "2410 Big Banana", "2024-10", "Banana"),
    ("knulli", "gladiator II", "2025-08-13", "gladiator II"),
    ("ROCKNIX", "20261010", "2026-10-10", "2026-10"),
    ("dArkOS", "08282026", "2026-08-28", "2026-08"),
    ("AmberELEC", "prerelease-20261003_1121", "2026-10-03", "2026-10"),
    ("spruce", "4.5.5", "", "4.5"),
    ("RetroDECK", "0.10.10b", "", "0.10"),
    ("spruce", "Unknown", "", "?"),
    ])
def test_matrix_major_version(cfw, version, released, expected):
    assert matrix.major_version({'cfw': cfw, 'cfw_version': version, 'released': released}) == expected


def test_matrix_device_grid(tmp_path):
    base = {'arch': "aarch64", 'python': "3.11.8", 'sdl': "SDL 2 28 5", 'portmaster': "2026-10-15_0969"}
    passed = [("install", suite.PASS, "installed", "")]
    failed = [("install", suite.FAIL, "not installed", "")]
    for name, info, states in (
            ("cube-old.zip", dict(cfw="knulli", cfw_version="scarab", device="rg-cubexx", started="2026-10-14T01:00:00"), failed),
            ("cube-new.zip", dict(cfw="knulli", cfw_version="scarab", device="rg-cubexx", started="2026-10-15T01:00:00"), passed),
            ("cube-spruce.zip", dict(cfw="spruce", cfw_version="4.5.5", device="Anbernic RG CubeXX", started="2026-10-15T02:00:00"), passed),
            ("h-muos.zip", dict(cfw="muOS", cfw_version="2601.0_JACARANDA", device="rg35xx-h", started="2026-10-15T03:00:00"), failed),
            ("odd.zip", dict(cfw="muOS", cfw_version="2601.0_JACARANDA", device="Mystery Box", started="2026-10-15T04:00:00"), passed),
            ):
        make_report(tmp_path, name, dict(base, **info), states, os_release="OS_DATE=20260819\n")

    rows = matrix.read_reports(tmp_path)
    assert {row['report']: row['device_name'] for row in rows}["cube-spruce.zip"] == "Anbernic RG CubeXX"
    catalogue = devices.build_catalogue({
        "Anbernic RG40XX H": {"knulli": {"device": "rg40xx-h", "manufacturer": "Anbernic"}},
        "Anbernic RG35XX H": {"muOS": {"device": "rg35xx-h", "manufacturer": "Anbernic"}},
        "Gameforce Ace": {"ROCKNIX": {"device": "ace", "manufacturer": "Gameforce"}},
        })

    tested, untested = matrix.grid_columns(rows, catalogue)
    assert tested == [("knulli", ["scarab"]), ("muOS", ["Jacaranda"]), ("spruce", ["4.5"])]
    assert untested == ["ROCKNIX"]
    assert [device.name for device, _ in matrix.grid_devices(rows, catalogue)] == [
        "Anbernic RG35XX H", "Anbernic RG40XX H", "Anbernic RG CubeXX", "Gameforce Ace", "Mystery Box"]

    page = matrix.render_html(rows, catalogue=catalogue)
    assert "<script" not in page
    ## knulli's CubeXX: 2 reports, passing now after a failure; its link goes to its setup row.
    cell = re.search(r'<td class="v first c mixed h2" title="Anbernic RG CubeXX · knulli scarab\n2 reports[^"]*"><a href="#(setup-\d+)">2</a></td>', page)
    assert cell and f'<tr id="{cell.group(1)}">' in page
    assert re.search(r'<td class="v first c fail h1" title="Anbernic RG35XX H · muOS Jacaranda', page)
    ## The RG40XX H has no reports: tinted where its family has some, marked where knulli supports it.
    assert re.search(r'<td class="v first c family gap" title="Anbernic RG40XX H · knulli scarab\nNo reports, but 2 from its family', page)
    assert '<td class="u first c gap" title="Gameforce Ace · ROCKNIX' in page
    assert ">H700)<" not in page and ">RGxxXX (H700)<" in page
    assert "Of the 3 device and CFW pairs PortMaster-Info lists, 1 have a report" in page
    assert '<td class="n">5</td></tr></tfoot>' in page


def test_dialog_waits_through_an_empty_done_file(tmp_path):
    ## Older pugwash truncates the done file before writing: empty isn't an answer (x55, 2026-10-13).
    class Running:
        def poll(self):
            return None

    dialog = Dialog(tmp_path / "nowhere", tmp_path)
    dialog.proc = Running()
    dialog.done.write_text("")

    writer = threading.Timer(0.3, lambda: dialog.done.write_text("OKAY"))
    writer.start()
    try:
        assert dialog._wait_done(timeout=10) == "OKAY"

    finally:
        writer.cancel()


def test_matrix_tells_same_soc_devices_apart(tmp_path):
    ## The TrimUI Brick and the MagicX Zero28 both say DEVICE_NAME=sun50iw10 on spruce.
    info = {'cfw': "spruce", 'cfw_version': "Unknown", 'device': "sun50iw10", 'arch': "aarch64"}
    states = [("install", suite.PASS, "installed", "")]
    make_report(tmp_path, "brick.zip", dict(info, started="1"), states,
                environment="DEVICE_NAME=sun50iw10\nDISPLAY_WIDTH=1024\nDISPLAY_HEIGHT=768\nDEVICE_RAM_MB=1024\n")
    make_report(tmp_path, "zero28.zip", dict(info, started="2"), states,
                environment="DEVICE_NAME=sun50iw10\nDISPLAY_WIDTH=640\nDISPLAY_HEIGHT=480\nDEVICE_RAM_MB=2048\n")
    ## Newer reports carry it in info, spruce's PLATFORM too.
    make_report(tmp_path, "flip.zip", dict(info, started="3", device="MIYOO RK3566 355 V10 Board", platform="Flip",
                                           display="640x480", ram_mb="1024"), states)

    rows = matrix.read_reports(tmp_path)
    assert len(matrix.group_rows(rows)) == 3

    page = matrix.render_html(rows)
    assert "1024x768 · 1 GB" in page and "640x480 · 2 GB" in page
    assert "MIYOO RK3566 355 V10 Board (Flip)" in page


def test_device_details():
    output = 'some logging\nPMTEST_DEVICE_INFO {"model": "Powkiddy x55", "resolution": [1280, 720], "ram": 4096}\n'
    assert suite.device_details(output, {'PLATFORM': "Brick"}) == {
        'model': "Powkiddy x55", 'display': "1280x720", 'ram_mb': "4096", 'platform': "Brick"}

    assert suite.device_details("crashed\n", {}) == {}
    assert suite.device_details("PMTEST_DEVICE_INFO {not json\n", {}) == {}


BRICK_WARNING = ("/mnt/SDCARD/Roms/ports/pmtest/tree/PortMaster/exlibs/sdl2/dll.py:299: DLLWarning: "
                 "OSError('/mnt/SDCARD/spruce/brick/sdl2/libSDL2-2.0.so.0.3200.6: file too short')")


@pytest.mark.parametrize("output, summary", [
    ("SDL 2 30 8\nDRIVERS mali\n", ("SDL 2 30 8", "")),
    ## pysdl2 skipped a broken library first: the version is the next line (spruce, TrimUI Brick).
    (BRICK_WARNING + "\n  warn(...)\nSDL 2 30 8\nDRIVERS mali\n", ("SDL 2 30 8", "libSDL2-2.0.so.0.3200.6: file too short")),
    ("Traceback (most recent call last):\nOSError: could not find any library for SDL2\n", ("broken", "")),
    ("", ("broken", "")),
    ])
def test_sdl_summary(output, summary):
    assert suite.sdl_summary(output) == summary


def test_matrix_sdl_column(tmp_path):
    states = [("install", suite.PASS, "installed", "")]
    ## A report from before sdl_summary: info['sdl'] is the warning, the version is in device/sdl.txt.
    old = make_report(tmp_path, "old.zip", {'cfw': "spruce", 'device': "Brick", 'sdl': BRICK_WARNING}, states)
    with zipfile.ZipFile(old, "a") as zf:
        zf.writestr("device/sdl.txt", BRICK_WARNING + "\nSDL 2 30 8\nDRIVERS mali\n")

    make_report(tmp_path, "new.zip", {'cfw': "muOS", 'device': "rg35xx-h", 'sdl': "SDL 2 28 5"}, states)
    make_report(tmp_path, "broken.zip", {'cfw': "x", 'device': "y", 'sdl': "broken"}, states)

    rows = {row['report']: row for row in matrix.read_reports(tmp_path)}
    assert (rows["old.zip"]['sdl'], rows["old.zip"]['sdl_warned']) == ("2.30.8", True)
    assert (rows["new.zip"]['sdl'], rows["new.zip"]['sdl_warned']) == ("2.28.5", False)
    assert rows["broken.zip"]['sdl'] == "broken"
    assert "file too short" not in matrix.render_html(list(rows.values()))


@pytest.mark.parametrize("drivers, stops", [
    (["dummy", "x11"], False),
    (["offscreen", "kmsdrm"], False),
    (["kmsdrm"], True),
    ])
def test_step_gui_dialog(monkeypatch, drivers, stops):
    ## Headless GUI tests keep the dialog up with a message; on the real screen pugwash lets go of it.
    ## Either way the dialog after them is a new one.
    events = []

    class FakeSuite(suite.Suite):
        def __init__(self):
            self.info = {'video_drivers': drivers}
            self.has_ui = True

        def say(self, text):
            events.append(("say", self.has_ui))

        def ui_stop(self):
            events.append(("stop", None))
            self.has_ui = False

        def ui_start(self):
            events.append(("start", None))
            self.has_ui = True

        def _pytest(self, name, marker, timeout, extra_env=None, label=""):
            events.append(("pytest", self.has_ui))
            return {'tests': 1, 'passed': 1, 'failed': 0, 'errors': 0, 'skipped': 0, 'failures': [], 'skip_reasons': {}}

    monkeypatch.setattr(suite.time, "sleep", lambda seconds: None)
    section = suite.Section("gui", "GUI tests")
    FakeSuite().step_gui(section)

    assert [has_ui for kind, has_ui in events if kind == "pytest"] == [not stops] * (2 if stops else 1)
    ## A fresh dialog afterwards either way (Mali fbdev lost the kept one's images).
    assert events[-2:] == [("stop", None), ("start", None)]
    assert section.status == suite.PASS


################################################################################
## Sending reports: suite.send_report and tools/test_suite/receive.py.
def test_upload_url(tmp_path):
    upload = tmp_path / "upload.txt"
    assert suite.upload_url(upload) is None

    upload.write_text("# where reports go\n\n  http://192.168.1.2:8770/ \n")
    assert suite.upload_url(upload) == "http://192.168.1.2:8770/"


def test_receive_clean_name():
    assert receive.clean_name("ROCKNIX-x55-20261013-1500.zip") == "ROCKNIX-x55-20261013-1500.zip"
    assert receive.clean_name("../../etc/passwd") == "passwd.zip"
    assert receive.clean_name("a b/c d?.zip") == "c_d_.zip"
    assert receive.clean_name("..").startswith("report-")
    assert receive.clean_name(None).startswith("report-")


@pytest.fixture
def receiver(tmp_path):
    import http.server

    lines = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), receive.make_handler(tmp_path / "got", log=lines.append))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/", tmp_path / "got", lines
    server.shutdown()
    server.server_close()


def test_send_report(tmp_path, receiver):
    url, got, lines = receiver
    report = make_report(tmp_path, "knulli-RG35XX-H-20261014-0348.zip", {'cfw': "knulli", 'device': "RG35XX-H"},
                         [("install", suite.PASS, "installed", "")])

    assert suite.send_report(url, report) == (True, "")
    assert suite.send_report(url, report) == (True, "")
    assert sorted(path.name for path in got.iterdir()) == ["knulli-RG35XX-H-20261014-0348-1.zip", "knulli-RG35XX-H-20261014-0348.zip"]
    assert (got / "knulli-RG35XX-H-20261014-0348.zip").read_bytes() == report.read_bytes()
    assert "knulli" in lines[0] and "install=pass" in lines[0]

    ## Not a report: refused, nothing saved.
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    ok, why = suite.send_report(url, junk)
    assert not ok and "400" in why
    assert len(list(got.iterdir())) == 2

    ## Nobody listening.
    ok, why = suite.send_report("http://127.0.0.1:9/", report, timeout=5)
    assert not ok and why


def test_ssl_context():
    ## PortMaster's certifi bundle, not the device's: some CFWs have none.
    context = suite.ssl_context()
    assert context.verify_mode == suite.ssl.CERT_REQUIRED
    assert len(context.get_ca_certs()) > 100


def test_summary_entries_sent():
    sections = [suite.Section("install", "Install PortMaster")]
    sections[0].set(suite.PASS, "installed")

    def texts(sent):
        entries = {key: desc for key, title, desc in suite.summary_entries(sections, "r.zip", sent)}
        return entries["#overall"], entries["#report"]

    overall, report = texts(None)
    assert "Please send the report" in overall and "Uploaded" not in report

    overall, report = texts((True, ""))
    assert "uploaded to be processed" in overall and "Please send" not in overall and report.endswith("Uploaded.")

    overall, report = texts((False, "timed out"))
    assert "Please send the report" in overall and "Couldn't upload it (timed out)" in report


def test_pending_reports(tmp_path):
    ## Reports from earlier runs: uploaded ones are done, kept/failed ones are offered again.
    first = make_report(tmp_path, "a.zip", {'portmaster': "2026-10-14_0169"}, [("install", suite.PASS, "installed", "")])
    second = make_report(tmp_path, "b.zip", {'portmaster': "2026-10-14_0469"}, [("install", suite.PASS, "installed", "")])
    os.utime(str(first), (1000, 1000))
    (tmp_path / "junk.zip").write_bytes(b"not a zip")
    os.utime(str(tmp_path / "junk.zip"), (2000, 2000))

    assert suite.report_version(second) == "2026-10-14_0469"
    assert suite.report_version(tmp_path / "junk.zip") is None
    assert suite.pending_reports(tmp_path) == [(first, "2026-10-14_0169", False), (tmp_path / "junk.zip", None, False), (second, "2026-10-14_0469", False)]

    suite.mark_report(first, "kept")
    suite.mark_report(tmp_path / "junk.zip", "uploaded")
    assert suite.pending_reports(tmp_path) == [(first, "2026-10-14_0169", True), (second, "2026-10-14_0469", False)]

    ## Uploading later replaces "kept".
    suite.mark_report(first, "uploaded")
    assert not suite.report_marker(first, "kept").exists()
    assert suite.pending_reports(tmp_path) == [(second, "2026-10-14_0469", False)]


def test_upload_question():
    report = Path("r.zip")
    assert suite.upload_question([(report, "2026-10-14_0469", True)]) == (
        "I see you've already run PortMaster 2026-10-14_0469 and chose not to upload it.\n\nWould you like to upload it now?")
    assert "couldn't be uploaded" in suite.upload_question([(report, "2026-10-14_0469", False)])
    assert suite.upload_question([(report, None, True)]).startswith("I see you've already run the Test Suite and")
    assert suite.upload_question([(report, "a", True), (report, "b", False)]).startswith("I see 2 earlier runs")


class FakeUI:
    def __init__(self, answers):
        self.answers = list(answers)
        self.boxes = []

    def message_box(self, text, **kwargs):
        self.boxes.append(text)
        return self.answers.pop(0) if self.answers else True


def offer_suite(ui):
    class OfferSuite(suite.Suite):
        def __init__(self):
            self.ui = ui
            self.has_ui = True

        def log(self, text):
            pass

        def say(self, text):
            pass

    return OfferSuite()


def test_offer_pending_uploads(tmp_path, monkeypatch, receiver):
    url, got, lines = receiver
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(suite, "REPORTS", reports)
    report = make_report(reports, "old.zip", {'portmaster': "2026-10-14_0469"}, [("install", suite.PASS, "installed", "")])
    suite.mark_report(report, "kept")

    ## Not now: stays pending, asked again next time.
    ui = FakeUI([False])
    offer_suite(ui).offer_pending_uploads(url)
    assert ui.boxes == [suite.upload_question([(report, "2026-10-14_0469", True)])]
    assert not got.exists() and suite.pending_reports(reports)

    ## Upload: sent, marked, and asked no more.
    ui = FakeUI([True])
    offer_suite(ui).offer_pending_uploads(url)
    assert ui.boxes[-1] == "Uploaded, thanks!"
    assert [path.name for path in got.iterdir()] == ["old.zip"]
    assert suite.pending_reports(reports) == []

    ui = FakeUI([])
    offer_suite(ui).offer_pending_uploads(url)
    assert ui.boxes == []


def test_offer_pending_uploads_fails(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(suite, "REPORTS", reports)
    make_report(reports, "old.zip", {}, [("install", suite.PASS, "installed", "")])
    monkeypatch.setattr(suite, "send_report", lambda url, report: (False, "no internet"))

    ui = FakeUI([True])
    offer_suite(ui).offer_pending_uploads("https://example.invalid/")
    assert ui.boxes[-1].startswith("Couldn't upload 1 of 1 report(s): no internet")
    assert len(suite.pending_reports(reports)) == 1


def test_logs_set_aside(tmp_path):
    ## The tester's PortMaster logs stay out of the report and come back afterwards.
    pm, saved = tmp_path / "PortMaster", tmp_path / "pmtest" / "saved-logs"
    pm.mkdir()
    (pm / "pugwash.txt").write_text("two years of history\n")
    (pm / "log.txt").write_text("last launch\n")

    suite.set_aside_logs(pm, saved)
    assert (pm / "pugwash.txt").read_text() == "" and (pm / "log.txt").read_text() == ""
    assert not (pm / "harbourmaster.txt").exists()

    ## The run logs things, then everything is put back as it was.
    (pm / "pugwash.txt").write_text("the run\n")
    (pm / "harbourmaster.txt").write_text("the run\n")
    suite.restore_logs(pm, saved)
    assert (pm / "pugwash.txt").read_text() == "two years of history\n"
    assert (pm / "log.txt").read_text() == "last launch\n"
    assert (pm / "harbourmaster.txt").read_text() == "the run\n"
    assert not saved.exists()


def test_logs_after_a_crash(tmp_path):
    ## A run that never restored them: the next run does, keeping what was logged since.
    pm, saved = tmp_path / "PortMaster", tmp_path / "saved-logs"
    pm.mkdir()
    (pm / "pugwash.txt").write_text("old\n")
    suite.set_aside_logs(pm, saved)
    (pm / "pugwash.txt").write_text("crashed run, then PortMaster used\n")

    suite.set_aside_logs(pm, saved)
    assert (pm / "pugwash.txt").read_text() == ""
    suite.restore_logs(pm, saved)
    assert (pm / "pugwash.txt").read_text() == "old\ncrashed run, then PortMaster used\n"


def test_main_restores_logs(tmp_path, monkeypatch):
    pm = tmp_path / "PortMaster"
    pm.mkdir()
    (pm / "pugwash.txt").write_text("theirs\n")
    monkeypatch.setattr(suite, "SAVED_LOGS", tmp_path / "saved-logs")

    class CrashingSuite(suite.Suite):
        def __init__(self):
            self.controlfolder = pm
            self.has_ui = False

        def run_suite(self):
            assert (pm / "pugwash.txt").read_text() == ""
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        CrashingSuite().main()

    assert (pm / "pugwash.txt").read_text() == "theirs\n"


def test_step_smoke_fetches_the_port_list(tmp_path, monkeypatch):
    ## A PortMaster that was never opened has no port list, so the online test can't use --no-check.
    commands = []

    class SmokeSuite(suite.Suite):
        def __init__(self):
            self.work = tmp_path
            self.controlfolder = tmp_path / "PortMaster"

        def say(self, text):
            pass

        def test_env(self, **extra):
            return dict(extra)

        def run(self, command, timeout=600, env=None, cwd=None, output=None):
            commands.append([str(arg) for arg in command])
            if command[-2:] == ["install", suite.SMOKE_PORT]:
                (Path(env["HM_PORTS_DIR"]) / suite.SMOKE_SCRIPT).write_text("")
            elif command[-2:] == ["uninstall", suite.SMOKE_PORT]:
                (Path(env["HM_PORTS_DIR"]) / suite.SMOKE_SCRIPT).unlink()
            return 0, ""

    monkeypatch.setattr(suite.socket, "create_connection", lambda *args, **kwargs: io.BytesIO())
    section = suite.Section("smoke", "Online install test")
    SmokeSuite().step_smoke(section)

    assert section.status == suite.PASS, section.details
    assert len(commands) == 4
    assert not any("--no-check" in command for command in commands)
