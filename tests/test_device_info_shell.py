# SPDX-License-Identifier: MIT
#
# device_info.txt itself, run on this machine. Ports run it through whatever
# /bin/bash is, and on some firmwares (TrimUI Smart Pro 1.0.4) that's BusyBox.

import re
import shutil
import subprocess

import pytest

from conftest import PM_DIR

SHELLS = [("bash",), ("busybox", "sh")]


def shell_or_skip(shell):
    if shutil.which(shell[0]) is None:
        pytest.skip(f"needs {shell[0]}")

    return list(shell)


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
def test_device_info_parses(shell):
    command = shell_or_skip(shell)
    result = subprocess.run(command + ["-n", str(PM_DIR / "device_info.txt")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert result.returncode == 0, result.stdout


def run_device_info(command, tmp_path):
    folder = tmp_path / command[0]
    folder.mkdir()
    shutil.copy(str(PM_DIR / "device_info.txt"), str(folder / "device_info.txt"))
    env = {'PATH': "/usr/bin:/bin:/usr/sbin:/sbin", 'controlfolder': str(folder), 'HOME': str(tmp_path)}
    result = subprocess.run(
        command + [str(folder / "device_info.txt"), "-f"], cwd=str(folder), env=env, timeout=120,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    ## Probes may grumble on stderr on a device; a shell that can't run it says so.
    assert result.returncode == 0, result.stderr
    assert "syntax error" not in result.stderr, result.stderr

    cached = list(folder.glob("device_info_*.env"))
    assert len(cached) == 1, (result.stdout, list(folder.iterdir()))
    return cached[0].name, cached[0].read_text()


def test_device_info_same_in_busybox(tmp_path):
    ## The same answers, and a cache file, whichever shell runs it.
    bash = run_device_info(shell_or_skip(SHELLS[0]), tmp_path)
    busybox = run_device_info(shell_or_skip(SHELLS[1]), tmp_path)

    assert bash == busybox
    assert "DEVICE_CAPABILITIES=" in bash[1] and "analog_0" in bash[1]
    assert "/" not in bash[0]


def run_fragment(command, script, root):
    """Run part of device_info.txt: in root, with nothing from this process's environment
    (in RetroDECK's Flatpak FLATPAK_ID makes it RetroDECK), stdout only (bash warns on stderr
    when pytest has already removed the folder it was started in)."""
    result = subprocess.run(command + ["-c", script], cwd=str(root), env={'PATH': "/usr/bin:/bin:/usr/sbin:/sbin"},
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def run_version_block(command, root, cfw_name):
    ## Just the CFW_VERSION section, with its absolute paths moved under root.
    text = (PM_DIR / "device_info.txt").read_text()
    block = text[text.index('export CFW_VERSION="Unknown"'):text.index("# 3c.")]
    block = re.sub(r'(?<=[\s"])/(etc|usr|boot|userdata|opt|var|mnt)/', lambda m: f"{root}/{m.group(1)}/", block)
    script = f'CFW_NAME="{cfw_name}"\n{block}\necho "$CFW_VERSION"\n'
    return run_fragment(command, script, root)


KNULLI_OS_RELEASE = 'NAME=Batocera.linux\nPRETTY_NAME=\\"Batocera.linux {0}\\"\nVERSION={0}\nID=buildroot\nVERSION_ID=2024.11\nOS_NAME="knulli"\n'


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
@pytest.mark.parametrize("cfw_name", ["knulli", "Batocera.linux"])
@pytest.mark.parametrize("version", ["gladiator", "42", "44-dev"])
def test_knulli_version_from_os_release(shell, cfw_name, version, tmp_path):
    ## knulli has no knulli.version file: the version is Batocera's VERSION=, not
    ## Buildroot's VERSION_ID, and never a made-up "scarab".
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "os-release").write_text(KNULLI_OS_RELEASE.format(version))

    assert run_version_block(shell_or_skip(shell), tmp_path, cfw_name) == version


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
def test_knulli_version_files(shell, tmp_path):
    command = shell_or_skip(shell)
    (tmp_path / "usr" / "share" / "batocera").mkdir(parents=True)
    (tmp_path / "usr" / "share" / "batocera" / "batocera.version").write_text("41 2024/12/10 12:00\n")
    assert run_version_block(command, tmp_path, "knulli") == "41"

    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "os-release").write_text(KNULLI_OS_RELEASE.format("42"))
    assert run_version_block(command, tmp_path, "knulli") == "42"

    (tmp_path / "etc" / "knulli.version").write_text("gladiator\r\n")
    assert run_version_block(command, tmp_path, "knulli") == "gladiator"

    ## Where knulli keeps it (TrimUI Brick Pro): its own name, not Batocera's 42.
    (tmp_path / "usr" / "share" / "knulli").mkdir(parents=True)
    (tmp_path / "usr" / "share" / "knulli" / "knulli.version").write_text("scarab 2026/08/19 16:06\n")
    assert run_version_block(command, tmp_path, "knulli") == "scarab"


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
def test_knulli_version_unknown(shell, tmp_path):
    assert run_version_block(shell_or_skip(shell), tmp_path, "knulli") == "Unknown"


def run_cfw_blocks(command, root):
    ## CFW detection and the CFW_VERSION section, absolute paths moved under root.
    text = (PM_DIR / "device_info.txt").read_text()
    detect = text[text.index('export CFW_NAME="Unknown"'):text.index('if [ "$CFW_NAME" = "Unknown" ] && ')]
    version = text[text.index('export CFW_VERSION="Unknown"'):text.index("# 3c.")]
    script = re.sub(r'(?<=[\s"])/(etc|usr|boot|userdata|opt|var|mnt|app|storage)/', lambda m: f"{root}/{m.group(1)}/", detect + version)
    return run_fragment(command, script + '\necho "$CFW_NAME|$CFW_VERSION"\n', root)


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
@pytest.mark.parametrize("title, expected", [
    ("ArkOS 2.0 (08242025)", "ArkOS|08242025"),
    ("ArkOS 2.0 (02012025)-3", "ArkOS|02012025-3"),      ## RG353M
    ("ArkOS 2.0 (01152023-1)", "ArkOS|01152023-1"),
    ("dArkOS (05102026)", "dArkOS|05102026"),
    ("dArkOSRE (09022026)", "dArkOSRE|09022026"),       ## mod_dArkOSRE.txt
    ("dArkOSen (09302026)", "dArkOS|09302026"),          ## an RG351MP's
    ("Welcome to dArkOS (09302026)", "dArkOS|09302026"),
    ("ArkOS wuMMLe (08242025)", "ArkOS wuMMLe|08242025"),  ## "mod_ArkOS wuMMLe.txt"
    ("ArkOS AeUX (08242025)", "ArkOS AeUX|08242025"),
    ("Welcome to ArkOS", "ArkOS|19.10"),               ## no date: Ubuntu's, as before
    ## From the old PortMaster hardware_info collection:
    ("ArkOS 2.0 (05242024)(AeUX)", "ArkOS AeUX|05242024"),
    ("ArkOS 351P/M wuMMLe (11052023)", "ArkOS wuMMLe|11052023"),
    (" *TheRA RC 1*", "TheRA|RC 1"),
    ("The R.A RC 1", "TheRA|RC 1"),
    ])
def test_arkos_name_and_version_from_boot_splash(shell, title, expected, tmp_path):
    command = shell_or_skip(shell)
    (tmp_path / "usr" / "share" / "plymouth" / "themes").mkdir(parents=True)
    (tmp_path / "usr" / "share" / "plymouth" / "themes" / "text.plymouth").write_text(f"[script]\ntitle={title}\r\n")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "os-release").write_text('NAME="Ubuntu"\nVERSION_ID="19.10"\n')

    assert run_cfw_blocks(command, tmp_path) == expected


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
@pytest.mark.parametrize("os_release, expected", [
    ## UnofficialOS names itself only in OS_NAME / OS_VERSION.
    ('OS_NAME="UnofficialOS"\nOS_VERSION="20230427"\nBUILD_ID="ed8922fe"\n', "UnofficialOS|20230427"),
    ## AmberELEC's own VERSION, not CoreELEC's VERSION_ID.
    ('NAME="AmberELEC"\nVERSION="20211122"\nID="coreelec"\nVERSION_ID="2021.01"\n', "AmberELEC|20211122"),
    ('NAME="AmberELEC"\nVERSION="prerelease-20261003_1121"\nVERSION_ID=""\n', "AmberELEC|prerelease-20261003_1121"),
    ('NAME="EmuELEC"\nVERSION="4.7"\nVERSION_ID="4.7"\n', "EmuELEC|4.7"),
    ])
def test_name_and_version_from_os_release(shell, os_release, expected, tmp_path):
    command = shell_or_skip(shell)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "os-release").write_text(os_release)

    text = (PM_DIR / "device_info.txt").read_text()
    detect = text[text.index('export CFW_NAME="Unknown"'):text.index("for dfile in")]
    version = text[text.index('export CFW_VERSION="Unknown"'):text.index("# 3c.")]
    script = re.sub(r'(?<=[\s"])/(etc|usr|boot|userdata|opt|var|mnt|app|storage)/', lambda m: f"{tmp_path}/{m.group(1)}/", detect + version)
    assert run_fragment(command, script + '\necho "$CFW_NAME|$CFW_VERSION"\n', tmp_path) == expected


@pytest.mark.parametrize("width, height", [
    (640, 480), (1280, 720), (720, 720), (480, 320), (1280, 800), (720, 480), (1240, 1080), (1080, 1240),
    (1024, 768), (1920, 1152), (320, 240), (854, 480)])
def test_screen_capabilities_shell_and_theme_server_agree(width, height):
    ## device_info.txt's screen rules (hires, wide, square, ...) and the theme server's copy of them
    ## (theme_server.worker.screen_capabilities): the preview pretends to be a device, so they must match.
    import math
    from theme_server import worker

    text = (PM_DIR / "device_info.txt").read_text()
    start = text.index('add_cap "${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}"')
    end = text.index('i=0', start)
    gcd = math.gcd(width, height)
    aspect_x, aspect_y = width // gcd, height // gcd
    if (aspect_x, aspect_y) == (8, 5):
        aspect_x, aspect_y = 16, 10
    script = ('add_cap() { echo "$1"; }\nDISPLAY_WIDTH=%d\nDISPLAY_HEIGHT=%d\nASPECT_X=%d\nASPECT_Y=%d\n' % (
        width, height, aspect_x, aspect_y)) + text[start:end]
    result = subprocess.run([shell_or_skip(SHELLS[0])[0], "-c", script], stdout=subprocess.PIPE, universal_newlines=True)
    assert set(result.stdout.split()) == set(worker.screen_capabilities(width, height))


## The version and a hash of the rest of device_info.txt. Devices keep their device_info_*.env
## while its DEVICE_INFO_VERSION matches (device_info.txt's fast path and hardware.py both reuse
## it), so a change without a new version never reaches a device that ran the old one: 0.2.6's
## new screen rules didn't, and the Retroid Pocket Classic stayed "wide".
DEVICE_INFO_HASH = ("0.2.8", "d9262aeab60d98c3")


def test_device_info_changes_come_with_a_new_version():
    import hashlib

    text = (PM_DIR / "device_info.txt").read_text(encoding="utf-8").replace("\r\n", "\n")
    version = re.search(r'(?m)^export DEVICE_INFO_VERSION="([^"]+)"$', text).group(1)
    digest = hashlib.sha256(re.sub(r'(?m)^export DEVICE_INFO_VERSION=.*$', "", text).encode("utf-8")).hexdigest()[:16]
    if version == DEVICE_INFO_HASH[0]:
        assert digest == DEVICE_INFO_HASH[1], (
            f"device_info.txt changed but DEVICE_INFO_VERSION is still {version}: raise it (devices keep their "
            f"cached device_info_*.env until it changes), then set DEVICE_INFO_HASH = (\"<new version>\", \"{digest}\")")
    else:
        assert False, f"DEVICE_INFO_VERSION is now {version}: set DEVICE_INFO_HASH = (\"{version}\", \"{digest}\")"


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
@pytest.mark.parametrize("machine, expected", [
    ## Mainline arm64: the SMCCC soc_id driver names the board, so the SoC comes from compatible.
    ("Anbernic RG CubeXX", "h700"),
    ## A soc0 driver that names the SoC itself.
    ("RK3566", "RK3566"),
    ])
def test_cpu_from_soc0_or_compatible(shell, machine, expected, tmp_path):
    command = shell_or_skip(shell)
    (tmp_path / "sys" / "devices" / "soc0").mkdir(parents=True)
    (tmp_path / "sys" / "devices" / "soc0" / "machine").write_text(machine + "\n")
    (tmp_path / "proc" / "device-tree").mkdir(parents=True)
    (tmp_path / "proc" / "device-tree" / "model").write_bytes(b"Anbernic RG CubeXX\0")
    (tmp_path / "proc" / "device-tree" / "compatible").write_bytes(b"anbernic,rgcubexx\0allwinner,sun50i-h700\0")

    text = (PM_DIR / "device_info.txt").read_text()
    block = text[text.index("detect_dynamic_cpu() {"):text.index('export DEVICE_CPU="$(detect_dynamic_cpu)"')]
    script = re.sub(r'(?<=[\s"])/(proc|sys)/', lambda m: f"{tmp_path}/{m.group(1)}/", block)
    assert run_fragment(command, script + '\ndetect_dynamic_cpu\n', tmp_path) == expected
