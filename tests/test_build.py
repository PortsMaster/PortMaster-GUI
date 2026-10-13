# SPDX-License-Identifier: MIT
#
# do_release.sh and the CFW bundle scripts, run for real into a tmp dist/.
#
# The build must never change the checkout, must only package what git knows about,
# and test builds are numbered YYYY-MM-DD_XX69.

import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import zipfile

import pytest

from conftest import PM_DIR, REPO_DIR


pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("zip", "unzip", "msgfmt", "git", "bash")) or
    not (REPO_DIR / ".git").exists(),
    reason="needs zip, unzip, msgfmt, bash and a git checkout")

TODAY = datetime.date.today().strftime("%Y-%m-%d")


def run(script, *args, check=True, **env):
    run_env = dict(os.environ)
    run_env.update(env)
    result = subprocess.run(
        ["bash", str(REPO_DIR / script), *args], cwd=str(REPO_DIR), env=run_env, timeout=300,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    if check:
        assert result.returncode == 0, result.stdout

    return result


def git_status():
    """Everything git sees in the checkout, ignored files too (an old build left .mo files,
    version, ...). Not coverage data: under pytest-cov any python the build runs writes one."""
    output = subprocess.check_output(
        ["git", "status", "--porcelain", "--ignored", "--untracked-files=all"], cwd=str(REPO_DIR), universal_newlines=True)

    return sorted(
        line for line in output.splitlines()
        if "/.coverage" not in "/" + line[3:] and "__pycache__" not in line)


def zip_names(data):
    with zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data) as zf:
        return set(zf.namelist())


@pytest.fixture(scope="module")
def test_build(tmp_path_factory):
    """One `./do_release.sh test`, and what the checkout looked like around it."""
    dist = tmp_path_factory.mktemp("dist")
    pugwash = (PM_DIR / "pugwash").read_bytes()
    before = git_status()

    output = run("do_release.sh", "test", PM_DIST_DIR=str(dist)).stdout

    return {
        'dist': dist,
        'output': output,
        'status': (before, git_status()),
        'pugwash_changed': pugwash != (PM_DIR / "pugwash").read_bytes(),
        }


def test_checkout_untouched(test_build):
    before, after = test_build['status']
    assert sorted(set(after) - set(before)) == []
    assert sorted(set(before) - set(after)) == []
    assert not test_build['pugwash_changed']


def test_test_version(test_build):
    dist = test_build['dist']
    assert (dist / "version").read_text().strip() == f"{TODAY}_0069"
    assert (dist / "test-builds.txt").read_text().split() == [f"{TODAY}_0069"]
    ## No version.json, no installers: test builds aren't published.
    assert sorted(path.name for path in dist.iterdir()) == ["PortMaster.zip", "test-builds.txt", "version"]


def test_next_test_version(tmp_path):
    (tmp_path / "test-builds.txt").write_text(f"{TODAY}_0069\n{TODAY}_0169\n2020-01-01_0269\n")
    result = run("do_release.sh", "test", PM_DIST_DIR=str(tmp_path), PM_PRINT_VERSION="Y")
    assert result.stdout.strip() == f"{TODAY}_0269"


def test_release_version_format(tmp_path):
    result = run("do_release.sh", "beta", PM_DIST_DIR=str(tmp_path), PM_PRINT_VERSION="Y")
    assert re.fullmatch(r"\d{4}\.\d\d\.\d\d-\d{4}", result.stdout.strip())


def test_unknown_channel(tmp_path):
    result = run("do_release.sh", "nightly", check=False, PM_DIST_DIR=str(tmp_path))
    assert result.returncode != 0
    assert "Unknown release channel" in result.stdout


def test_portmaster_zip_contents(test_build):
    names = zip_names(test_build['dist'] / "PortMaster.zip")

    assert {"PortMaster/pugwash", "PortMaster/harbourmaster", "PortMaster/pylibs.zip",
            "PortMaster/PortMaster.sh", "PortMaster/utils/pm_launch.txt", "PortMaster/version",
            "PortMaster/muos/PortMaster.txt", "PortMaster/control.txt"} <= names

    assert all(name.startswith("PortMaster/") for name in names)
    junk = [name for name in names if (
        name.startswith(("PortMaster/pylibs/", "PortMaster/exlibs/", "PortMaster/config/", "PortMaster/themes/")) or
        "__pycache__" in name or name.endswith((".squashfs", ".pyc", "harbourmaster.txt", "pugwash.txt")))]
    assert junk == []


def test_version_stamped(test_build):
    with zipfile.ZipFile(test_build['dist'] / "PortMaster.zip") as zf:
        pugwash = zf.read("PortMaster/pugwash").decode()
        version = zf.read("PortMaster/version").decode().strip()

    assert f"PORTMASTER_VERSION = '{TODAY}_0069'" in pugwash
    assert "PORTMASTER_RELEASE_CHANNEL = 'beta'" in pugwash
    assert version == f"{TODAY}_0069"


def test_pylibs_zip_contents(test_build):
    with zipfile.ZipFile(test_build['dist'] / "PortMaster.zip") as zf:
        names = zip_names(zf.read("PortMaster/pylibs.zip"))

    assert {"pylibs/pugwash/app.py", "pylibs/harbourmaster/platform/__init__.py",
            "pylibs/harbourmaster/platform.py", "exlibs/loguru/__init__.py",
            "pylibs/locales/de_DE/LC_MESSAGES/messages.mo"} <= names

    assert [name for name in names if "__pycache__" in name or name.endswith(".pyc")] == []
    ## Every translation is compiled.
    for po_file in (PM_DIR / "pylibs" / "locales").glob("*/LC_MESSAGES/*.po"):
        assert str(po_file.relative_to(PM_DIR).with_suffix(".mo")) in names


def test_release_updates_version_json(tmp_path):
    version_json = tmp_path / "version.json"
    old = {channel: {"version": "2026.01.01-0000", "url": "old", "md5": "old"} for channel in ("alpha", "beta", "stable")}
    version_json.write_text(json.dumps(old))
    dist = tmp_path / "dist"

    run("do_release.sh", "beta", "2026.10.13-1234", PM_DIST_DIR=str(dist), PM_VERSION_JSON=str(version_json))

    data = json.loads((dist / "version.json").read_text())
    md5 = hashlib.md5((dist / "PortMaster.zip").read_bytes()).hexdigest()

    ## beta updates the beta and alpha channels, stable stays.
    for channel in ("alpha", "beta"):
        assert data[channel] == {
            "version": "2026.10.13-1234", "md5": md5,
            "url": "https://github.com/PortsMaster/PortMaster-GUI/releases/download/2026.10.13-1234/PortMaster.zip"}

    assert data["stable"] == old["stable"]
    assert (dist / "version").read_text().strip() == "2026.10.13-1234"
    ## The file it was given is left as it was.
    assert json.loads(version_json.read_text()) == old


@pytest.mark.parametrize("script, launcher, stub", [
    ("do_muos_release.sh", "mnt/mmc/MUOS/PortMaster/PortMaster.sh", "muos"),
    ("do_trimui_release.sh", "Apps/PortMaster/launch.sh", "trimui"),
    ("do_x86_64_release.sh", "PortMaster/PortMaster.sh", "retrodeck"),
    ])
def test_cfw_bundles(test_build, tmp_path, script, launcher, stub):
    dist = tmp_path / "dist"
    dist.mkdir()
    shutil.copy(str(test_build['dist'] / "PortMaster.zip"), str(dist))

    run(script, PM_DIST_DIR=str(dist))

    bundle = next(dist.glob("*.portmaster.zip"))
    with zipfile.ZipFile(bundle) as zf:
        assert zf.read(launcher).decode() == (PM_DIR / stub / "PortMaster.txt").read_text()
