# SPDX-License-Identifier: MIT
#
# Autoinstall (pugwash/autoinstall.py and the fifo "autoinstall" command the launchers
# call): the install order, runtimes architecture checks, what is deleted / kept,
# the summary page and the answer the launcher gets.

import zipfile

import pytest

import harbourmaster
from pugwash import autoinstall

from conftest import RecordingCallback, basic_port_files, write_port_zip, write_raw_zip


def write_runtimes_zip(zip_path, comment=None, files=("test.squashfs", )):
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for name in files:
            zf.writestr(name, b"squash")

        if comment is not None:
            zf.comment = comment.encode()

    return zip_path


def write_portmaster_zip(zip_path):
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("PortMaster/autoinstall-test.txt", "new PortMaster")

    return zip_path


@pytest.fixture
def dirs(tmp_path):
    dir_1 = tmp_path / "pm_autoinstall"
    dir_2 = tmp_path / "ports_autoinstall"
    dir_1.mkdir()
    dir_2.mkdir()
    return dir_1, dir_2


## -- finding files

def test_find_order_and_kinds(dirs):
    dir_1, dir_2 = dirs
    write_portmaster_zip(dir_2 / "PortMaster.zip")
    write_portmaster_zip(dir_1 / "PortMaster.zip")
    write_runtimes_zip(dir_1 / "runtimes.zip")
    write_runtimes_zip(dir_2 / "runtimes.full.aarch64.zip", "aarch64")
    (dir_2 / "mono-6.12.0.122-aarch64.squashfs").write_bytes(b"squash")
    write_raw_zip(dir_1 / "b.zip", b"x")
    write_raw_zip(dir_2 / "a.zip", b"x")
    (dir_1 / "readme.txt").write_text("not installed")

    files = autoinstall.find_autoinstall_files([dir_1, dir_2, dir_1 / "missing"])

    ## Only the first PortMaster.zip, the first directory wins.
    assert files['portmaster'] == [dir_1 / "PortMaster.zip"]
    assert files['runtimes'] == [dir_1 / "runtimes.zip", dir_2 / "runtimes.full.aarch64.zip"]
    assert files['squashfs'] == [dir_2 / "mono-6.12.0.122-aarch64.squashfs"]
    assert files['ports'] == [dir_1 / "b.zip", dir_2 / "a.zip"]


def test_find_same_dir_twice(dirs):
    ## spruce passes one directory twice.
    dir_1, _ = dirs
    write_raw_zip(dir_1 / "a.zip", b"x")

    assert autoinstall.find_autoinstall_files([dir_1, dir_1])['ports'] == [dir_1 / "a.zip"]
    assert autoinstall.has_autoinstall_files([dir_1])
    assert not autoinstall.has_autoinstall_files([dir_1 / "missing"])


@pytest.mark.parametrize("comment, arch", [
    (None, None),
    ("aarch64", "aarch64"),
    ("x86_64 runtimes built on 2026-01-01\n", "x86_64"),
    ("first line\narmhf", "armhf"),
    ])
def test_runtimes_zip_arch(tmp_path, comment, arch):
    assert autoinstall.runtimes_zip_arch(write_runtimes_zip(tmp_path / "r.zip", comment)) == arch


## -- installing (HarbourMaster + RecordingCallback, no GUI)

def run(hm, *dirs):
    callback = RecordingCallback()
    return autoinstall.run_autoinstall(hm, callback, dirs), callback


def test_port_installs_and_is_deleted(hm, dirs, hm_dirs):
    dir_1, dir_2 = dirs
    zip_file = write_port_zip(dir_2 / "testport.zip", basic_port_files())

    results, _ = run(hm, dir_1, dir_2)

    assert [(r.name, r.ok) for r in results] == [("testport.zip", True)]
    assert (hm_dirs['ports_dir'] / "Test Port.sh").is_file()
    assert not zip_file.exists()


def test_bad_port_is_kept_with_reason(hm, dirs, hm_dirs):
    dir_1, _ = dirs
    zip_file = write_raw_zip(dir_1 / "broken.zip", b"garbage")

    results, _ = run(hm, dir_1)

    assert len(results) == 1
    assert results[0].name == "broken.zip"
    assert not results[0].ok
    assert results[0].reason
    assert zip_file.exists()
    assert list(hm_dirs['ports_dir'].iterdir()) == []


def test_runtimes_right_arch(hm, dirs):
    dir_1, _ = dirs
    arch = hm.device['primary_arch']
    zip_file = write_runtimes_zip(dir_1 / f"runtimes.full.{arch}.zip", arch, files=("a.squashfs", "b.squashfs"))

    results, _ = run(hm, dir_1)

    assert [(r.name, r.ok) for r in results] == [(zip_file.name, True)]
    assert (hm.libs_dir / "a.squashfs").is_file()
    assert (hm.libs_dir / "b.squashfs").is_file()
    assert not zip_file.exists()


def test_old_runtimes_zip_without_comment(hm, dirs):
    dir_1, _ = dirs
    zip_file = write_runtimes_zip(dir_1 / "runtimes.zip")

    results, _ = run(hm, dir_1)

    assert results[0].ok
    assert (hm.libs_dir / "test.squashfs").is_file()
    assert not zip_file.exists()


@pytest.mark.parametrize("name, comment", [
    ("runtimes.full.wrong.zip", "wrongarch"),
    ("runtimes.zip", "wrongarch"),
    ("runtimes.popular.aarch64.zip", None),
    ])
def test_runtimes_wrong_arch_is_deleted(hm, dirs, name, comment):
    dir_1, _ = dirs
    zip_file = write_runtimes_zip(dir_1 / name, comment)

    results, _ = run(hm, dir_1)

    assert not results[0].ok
    assert "wrong architecture" in results[0].reason
    assert not zip_file.exists()
    assert not (hm.libs_dir / "test.squashfs").exists()


def test_runtimes_not_a_zip(hm, dirs):
    dir_1, _ = dirs
    zip_file = write_raw_zip(dir_1 / "runtimes.zip", b"garbage")

    results, _ = run(hm, dir_1)

    assert not results[0].ok
    assert zip_file.exists()


def test_squashfs_is_moved(hm, dirs):
    dir_1, _ = dirs
    (dir_1 / "godot_4.2.squashfs").write_bytes(b"squash")

    results, _ = run(hm, dir_1)

    assert results[0].ok
    assert (hm.libs_dir / "godot_4.2.squashfs").read_bytes() == b"squash"
    assert not (dir_1 / "godot_4.2.squashfs").exists()


def test_install_order(hm, dirs, monkeypatch):
    dir_1, dir_2 = dirs
    write_port_zip(dir_1 / "aaa.zip", basic_port_files())
    (dir_2 / "godot.squashfs").write_bytes(b"squash")
    write_runtimes_zip(dir_2 / "runtimes.zip")
    write_portmaster_zip(dir_2 / "PortMaster.zip")

    installed = []
    real_install = hm.install_port

    def install_port(name, *args, **kwargs):
        installed.append(name.rsplit('/', 1)[-1])
        if name.endswith("PortMaster.zip"):
            return 0

        return real_install(name, *args, **kwargs)

    monkeypatch.setattr(hm, "install_port", install_port)

    results, _ = run(hm, dir_1, dir_2)

    assert [r.name for r in results] == ["PortMaster.zip", "runtimes.zip", "godot.squashfs", "aaa.zip"]
    assert installed == ["PortMaster.zip", "aaa.zip"]
    assert all(r.ok for r in results)
    assert list(dir_1.iterdir()) == list(dir_2.iterdir()) == []


def test_portmaster_zip_installs(hm, dirs):
    dir_1, _ = dirs
    write_portmaster_zip(dir_1 / "PortMaster.zip")

    results, _ = run(hm, dir_1)

    assert results[0].ok, results
    assert (hm.tools_dir / "PortMaster" / "autoinstall-test.txt").is_file()
    assert not (dir_1 / "PortMaster.zip").exists()


def test_install_exception_is_a_failure(hm, dirs, monkeypatch):
    dir_1, _ = dirs
    zip_file = write_port_zip(dir_1 / "testport.zip", basic_port_files())

    def boom(name):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(hm, "install_port", boom)

    results, _ = run(hm, dir_1)

    assert [(r.ok, r.reason) for r in results] == [(False, "disk on fire")]
    assert zip_file.exists()


## -- summary

def test_summary_register():
    register = autoinstall.summary_register([
        autoinstall.AutoinstallResult("good.zip", True),
        autoinstall.AutoinstallResult("bad.zip", False, "port.json is broken"),
        ])

    assert list(register) == ['#total', '0', '1']
    assert register['#total']['title'] == "1 installed, 1 failed"
    assert register['0']['title'] == "OK: good.zip"
    assert register['1']['title'] == "FAILED: bad.zip"
    assert "port.json is broken" in register['1']['description']


## -- the fifo command, on the headless GUI

@pytest.fixture
def fifo(gui, hm_dirs, tmp_path, monkeypatch):
    gui.hm = harbourmaster.HarbourMaster({'offline': True, 'no-check': True}, callback=gui, **hm_dirs)

    done_file = tmp_path / "pm_done"
    done_file.write_text("WAIT")

    ## The summary waits for A: press it, and record what the page showed.
    monkeypatch.setattr(gui.events, "was_pressed", lambda button: button == 'A')
    shown = []
    real_show = gui.show_selection_list

    def show_selection_list(config, register):
        shown.append((config, register))
        return real_show(config, register)

    monkeypatch.setattr(gui, "show_selection_list", show_selection_list)

    config = {'done-file': done_file, 'register': {}}

    def autoinstall_cmd(*args):
        gui.fifo_autoinstall(config, [str(arg) for arg in args])
        return done_file.read_text()

    autoinstall_cmd.shown = shown
    yield autoinstall_cmd

    gui.hm = None


@pytest.mark.sdl
def test_fifo_okay(fifo, dirs, hm_dirs):
    dir_1, dir_2 = dirs
    write_port_zip(dir_2 / "testport.zip", basic_port_files())

    assert fifo(dir_1, dir_2) == "OKAY"
    assert (hm_dirs['ports_dir'] / "Test Port.sh").is_file()

    ((config, register), ) = fifo.shown
    assert config['want_description']
    assert register['#total']['title'] == "1 installed, 0 failed"


@pytest.mark.sdl
def test_fifo_fail(fifo, dirs, gui):
    dir_1, _ = dirs
    write_port_zip(dir_1 / "testport.zip", basic_port_files())
    write_raw_zip(dir_1 / "broken.zip", b"garbage")

    assert fifo(dir_1) == "FAIL"

    ((config, register), ) = fifo.shown
    assert register['#total']['title'] == "1 installed, 1 failed"
    assert gui.scene_list() == ["root"]


@pytest.mark.sdl
def test_fifo_nothing_to_do(fifo, dirs):
    assert fifo(*dirs) == "NONE"
    assert fifo.shown == []


@pytest.mark.sdl
def test_fifo_exception_still_answers(fifo, dirs, monkeypatch):
    dir_1, _ = dirs
    write_raw_zip(dir_1 / "broken.zip", b"garbage")

    def boom(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(autoinstall, "run_autoinstall", boom)

    assert fifo(dir_1) == "FAIL"


@pytest.mark.sdl
def test_fifo_requests_frontend_refresh(fifo, dirs, gui, monkeypatch):
    dir_1, _ = dirs
    write_port_zip(dir_1 / "testport.zip", basic_port_files())

    refreshed = []
    monkeypatch.setattr(gui, "request_frontend_refresh", lambda: refreshed.append(True))

    fifo(dir_1)
    assert refreshed == [True]


def test_summary_refresh_text():
    ## eg: RetroDECK, whose ES-DE PortMaster can't restart: say how to rescan.
    installed = [autoinstall.AutoinstallResult("good.zip", True)]
    failed = [autoinstall.AutoinstallResult("bad.zip", False, "broken")]

    register = autoinstall.summary_register(installed, "Rescan your games.")
    assert register['#total']['description'].endswith("\n\nRescan your games.")

    ## Nothing new to find.
    assert "Rescan" not in autoinstall.summary_register(failed, "Rescan your games.")['#total']['description']
    assert "Rescan" not in autoinstall.summary_register(installed)['#total']['description']


@pytest.mark.sdl
@pytest.mark.parametrize("es_name, expected", [("show-refresh", True), ("emulationstation", False)])
def test_fifo_summary_says_how_to_rescan(fifo, dirs, gui, monkeypatch, es_name, expected):
    dir_1, _ = dirs
    write_port_zip(dir_1 / "testport.zip", basic_port_files())
    monkeypatch.setattr(gui.hm.platform, "ES_NAME", es_name)
    monkeypatch.setattr(gui.hm.platform, "ROMS_REFRESH_TEXT", "\n\nMENU -> UTILITIES -> Rescan Rom Directory")
    monkeypatch.setattr(gui, "request_frontend_refresh", lambda: None)

    fifo(dir_1)

    ((config, register), ) = fifo.shown
    assert ("Rescan Rom Directory" in register['#total']['description']) is expected
