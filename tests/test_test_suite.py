# SPDX-License-Identifier: MIT
#
# The PortMaster Test Suite port (tools/test_suite): its results, summary and report,
# and its fifo client driving a real pugwash.

import json
import os
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
import matrix  # noqa: E402


def make_report(folder, name, info, states, environment=None):
    work = folder / ("work-" + name)
    work.mkdir(parents=True)
    if environment is not None:
        (work / "device").mkdir()
        (work / "device" / "environment.txt").write_text(environment)

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
    assert list(groups) == [("knulli", "scarab", "<rg-cubexx>"), ("muOS", "2601.0_JACARANDA", "rg35xx-h")]
    ## Newest run first.
    assert [row['report'] for row in groups[("muOS", "2601.0_JACARANDA", "rg35xx-h")]] == ["new.zip", "old.zip"]

    (test, message, found), = matrix.failure_index(rows)
    assert (test, message, len(found)) == ("tests.test_a::test_x", "assert 1 == 2", 2)

    page = matrix.render_html(rows)
    assert page.startswith("<title>PortMaster Test Matrix</title>")
    assert "&lt;rg-cubexx&gt;" in page and "<rg-cubexx>" not in page
    assert "<script" not in page

    assert matrix.main([str(reports), "--out", str(tmp_path / "out")]) == 0
    assert len(json.loads((tmp_path / "out" / "matrix.json").read_text())) == 3
    assert (tmp_path / "out" / "matrix.html").is_file()


def test_matrix_skips_oversized_summaries(tmp_path, monkeypatch):
    monkeypatch.setattr(matrix, "MAX_SUMMARY_BYTES", 10)
    make_report(tmp_path, "r.zip", {'cfw': "x"}, [("install", suite.PASS, "installed", "")])

    assert matrix.read_report(tmp_path / "r.zip") is None


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

    assert (("stop", None) in events) == stops
    assert (("start", None) in events) == stops
    assert [has_ui for kind, has_ui in events if kind == "pytest"] == [not stops] * (2 if stops else 1)
    assert section.status == suite.PASS
