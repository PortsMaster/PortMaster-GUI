# SPDX-License-Identifier: MIT
#
# The PortMaster Test Suite port (tools/test_suite): its results, summary and report,
# and its fifo client driving a real pugwash.

import json
import os
import sys
import zipfile

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


def test_pick_work_dir(tmp_path, monkeypatch):
    first, second = tmp_path / "tmpfs", tmp_path / "sdcard"

    assert suite.pick_work_dir([first, second], need_bytes=1) == first

    ## Not enough room anywhere: the last one.
    assert suite.pick_work_dir([first, second], need_bytes=1 << 62) == second


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
