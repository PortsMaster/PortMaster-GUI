# SPDX-License-Identifier: MIT
#
# On a device PortMaster ships as the two scripts plus pylibs.zip, which the
# scripts extract over pylibs/ and exlibs/ on first run. From a git checkout that
# step is skipped, so test it here with a copy that has no .git above it.

import os
import shutil
import subprocess
import sys
import zipfile

import pytest

from conftest import PM_DIR, start_fifo_gui


def build_pylibs_zip(zip_path):
    """Same contents as do_release.sh's `zip -9r pylibs.zip exlibs/ pylibs/ -x ...`."""
    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for top in ("exlibs", "pylibs"):
            for root, dirs, files in os.walk(str(PM_DIR / top)):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for name in files:
                    if name == ".DS_Store" or name.startswith("._"):
                        continue

                    if "NotoSans" in name and name.endswith(".ttf"):
                        continue

                    full = os.path.join(root, name)
                    zf.write(full, os.path.relpath(full, str(PM_DIR)))


@pytest.fixture(scope="module")
def release_dir(tmp_path_factory):
    pm_dir = tmp_path_factory.mktemp("release") / "PortMaster"
    pm_dir.mkdir()

    for script in ("pugwash", "harbourmaster"):
        shutil.copy2(str(PM_DIR / script), str(pm_dir / script))

    build_pylibs_zip(pm_dir / "pylibs.zip")
    return pm_dir


@pytest.fixture
def release_env(hm_dirs):
    env = dict(os.environ)
    env.update({
        'HM_TOOLS_DIR': str(hm_dirs['tools_dir']),
        'HM_PORTS_DIR': str(hm_dirs['ports_dir']),
        'HM_SCRIPTS_DIR': str(hm_dirs['scripts_dir']),
        })
    return env


def run_hm(release_dir, env, *args):
    result = subprocess.run(
        [sys.executable, str(release_dir / "harbourmaster"), "--offline", "--no-colour", *args],
        cwd=str(release_dir.parent), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    result.output = result.stdout.decode()
    return result


def test_first_run_extracts_pylibs(release_dir, release_env):
    result = run_hm(release_dir, release_env, "help")

    assert result.returncode == 0, result.output
    assert "- extracting new pylibs." in result.output
    assert "All available commands:" in result.output

    assert not (release_dir / "pylibs.zip").exists()
    assert (release_dir / "pylibs.zip.md5").is_file()
    assert (release_dir / "pylibs" / "harbourmaster" / "__init__.py").is_file()
    assert (release_dir / "exlibs" / "loguru" / "__init__.py").is_file()


def test_commands_after_extraction(release_dir, release_env, tmp_path):
    from conftest import basic_port_files, write_port_zip

    run_hm(release_dir, release_env, "help")

    assert run_hm(release_dir, release_env, "list").returncode == 0

    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())
    result = run_hm(release_dir, release_env, "install", str(zip_file))
    assert result.returncode == 0, result.output
    assert run_hm(release_dir, release_env, "uninstall", "testport.zip").returncode == 0


@pytest.mark.sdl
@pytest.mark.own_display
def test_pugwash_fifo_from_release(release_dir, release_env, tmp_path):
    ## Either script may be the one that extracts pylibs.zip.
    run_hm(release_dir, release_env, "help")

    gui = start_fifo_gui(release_dir, release_dir.parent, release_env, tmp_path)
    try:
        assert gui.send("messages_begin") == "DONE"
        assert gui.send("message", "Hello from a release layout") == "DONE"
        assert gui.send("messages_end") == "DONE"
        assert gui.exit() == 0

    finally:
        gui.kill()


@pytest.mark.sdl
@pytest.mark.own_display
def test_pugwash_starts_without_noto_fonts(release_env, tmp_path):
    ## The CJK fonts come from pylibs/resources/NotoSans.tar.xz on first run; without
    ## it (or with a broken one) pugwash still has to start, just without those fonts.
    pm_dir = tmp_path / "release" / "PortMaster"
    pm_dir.mkdir(parents=True)
    shutil.copy2(str(PM_DIR / "pugwash"), str(pm_dir / "pugwash"))
    build_pylibs_zip(pm_dir / "pylibs.zip")

    with zipfile.ZipFile(str(pm_dir / "pylibs.zip")) as zf:
        zf.extractall(str(pm_dir))

    (pm_dir / "pylibs.zip").unlink()
    ## (The PortMaster Test Suite's copy of the code doesn't have it to begin with.)
    noto_fonts = pm_dir / "pylibs" / "resources" / "NotoSans.tar.xz"
    if noto_fonts.exists():
        noto_fonts.unlink()

    gui = start_fifo_gui(pm_dir, pm_dir.parent, release_env, tmp_path)
    try:
        assert gui.send("message", "No CJK fonts") == "DONE"
        assert gui.exit() == 0

    finally:
        gui.kill()
