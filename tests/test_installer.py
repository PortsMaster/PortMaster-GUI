# SPDX-License-Identifier: MIT
#
# tools/installer.sh, the script inside Install.PortMaster.sh (and Restore.PortMaster.zip).
#
# It runs against a fake filesystem (PM_INSTALL_ROOT), with fake sudo / systemctl /
# curl / shutdown that write what they were asked to do into calls.txt. It must:
#  - find the same PortMaster directory as harbourmaster's config.detect_paths(),
#  - factory reset: remove everything in PortMaster/ except the runtimes,
#  - put this CFW's launcher where its frontend runs it,
#  - tell the frontend.

import os
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest

from conftest import PM_DIR, REPO_DIR


INSTALLER = REPO_DIR / "tools" / "installer.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("unzip") is None, reason="needs bash and unzip")

RD_JSON = (
    '{\n'
    '    "paths": {\n'
    '        "rd_home_path": "/run/media/deck/sd/retrodeck",\n'
    '        "roms_path": "/run/media/deck/sd/retrodeck/roms",\n'
    '        "portmaster_path": "/run/media/deck/sd/retrodeck/PortMaster"\n'
    '    }\n'
    '}\n')

XDG = "/userdata/system/.local/share"


def write_exe(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make(root, *paths):
    for path in paths:
        (root / path.lstrip("/")).mkdir(parents=True, exist_ok=True)


def link(root, path, target):
    """A symlink inside the fake root, eg: ArkOS's /opt/system/Tools is /roms2/tools."""
    link_path = root / path.lstrip("/")
    link_path.parent.mkdir(parents=True, exist_ok=True)
    (root / target.lstrip("/")).mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(root / target.lstrip("/"))


def write(root, path, text):
    file_path = root / path.lstrip("/")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text)
    return file_path


################################################################################
## The CFWs, as fake filesystems.
def fs_default(root):
    pass


def fs_spruce(root):
    make(root, "/mnt/SDCARD/spruce", "/mnt/SDCARD/Roms/ports")


def fs_trimui(root):
    make(root, "/mnt/SDCARD/Apps/PortMaster", "/mnt/SDCARD/Data/ports")


def fs_batocera(root):
    make(root, "/userdata/roms/ports", XDG)


def fs_muos(root):
    make(root, "/mnt/mmc/MUOS", "/mnt/mmc/ROMS/Ports")
    write_exe(root / "opt/muos/script/mux/quit.sh", 'echo "$(basename "$0") $*" >> "$FAKE_CALLS"\n')


def fs_arkos(root):
    link(root, "/opt/system/Tools", "/roms2/tools")
    make(root, "/roms2/ports")
    write(root, "/usr/share/plymouth/themes/text.plymouth", "title=ArkOS\n")
    write(root, "/etc/fstab", "/dev/mmcblk1p3 /roms2 vfat defaults 0 0\n")


def fs_arkos_one_card(root):
    link(root, "/opt/system/Tools", "/roms/tools")
    make(root, "/roms/ports")
    write(root, "/usr/share/plymouth/themes/text.plymouth", "title=ArkOS\n")
    write(root, "/etc/fstab", "")


def fs_opt_tools(root):
    make(root, "/opt/tools/PortMaster", "/roms/ports")


def fs_rocknix(root):
    make(root, "/storage/roms/ports")
    link(root, "/roms", "/storage/roms")
    write(root, "/etc/os-release", 'NAME="ROCKNIX"\nOS_NAME="ROCKNIX"\n')
    for name in ("PortMaster.sh", "control.txt", "portmaster.gptk", "mapper.txt"):
        write(root, f"/usr/config/PortMaster/{name}", f"rocknix {name}\n")


def fs_retrodeck(root):
    ## Inside RetroDECK's flatpak.
    write(root, "/var/config/retrodeck/retrodeck.json", RD_JSON)
    make(root, "/var/data", "/run/media/deck/sd/retrodeck/roms/portmaster")


def fs_retrodeck_outside(root):
    write(root, "/home/deck/.var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.json", RD_JSON)
    make(root, "/home/deck/.var/app/net.retrodeck.retrodeck/data", "/run/media/deck/sd/retrodeck/roms/portmaster")


CFWS = {
    'default':           fs_default,
    'spruce':            fs_spruce,
    'trimui':            fs_trimui,
    'batocera':          fs_batocera,
    'muos':              fs_muos,
    'arkos':             fs_arkos,
    'arkos_one_card':    fs_arkos_one_card,
    'opt_tools':         fs_opt_tools,
    'rocknix':           fs_rocknix,
    'retrodeck':         fs_retrodeck,
    'retrodeck_outside': fs_retrodeck_outside,
    }


class Installer:
    def __init__(self, tmp_path, cfw):
        self.root = tmp_path / "root"
        self.root.mkdir()
        self.work = tmp_path / "makeself"   # where makeself unpacks to
        self.work.mkdir()
        self.calls_file = tmp_path / "calls.txt"
        self.home = "/home/deck" if cfw.startswith("retrodeck") else "/root"
        (self.root / self.home.lstrip("/")).mkdir(parents=True, exist_ok=True)

        CFWS[cfw](self.root)

        bin_dir = tmp_path / "bin"
        log = 'echo "$(basename "$0") $*" >> "$FAKE_CALLS"\n'
        write_exe(bin_dir / "sudo", "exit 1\n")
        for tool in ("systemctl", "curl", "shutdown", "batocera-save-overlay"):
            write_exe(bin_dir / tool, log)

        self.env = {
            'PATH': f"{bin_dir}:{os.environ['PATH']}",
            'HOME': str(self.root / self.home.lstrip("/")),
            'XDG_DATA_HOME': XDG,
            'PM_INSTALL_ROOT': str(self.root),
            'PM_CUR_TTY': str(tmp_path / "tty"),
            'PM_INSTALL_SLEEP': "0",
            'FAKE_CALLS': str(self.calls_file),
            }

    def path(self, device_path):
        return self.root / str(device_path).lstrip("/")

    def detect(self):
        output = self.run(PM_INSTALL_DETECT="Y")
        return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)

    def run(self, **env):
        run_env = dict(self.env)
        run_env.update(env)
        ## $HOME is a device path inside the installer, the fake root is added to it.
        run_env['HOME'] = self.home
        result = subprocess.run(
            ["bash", str(INSTALLER)], cwd=str(self.work), env=run_env, timeout=120,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        assert result.returncode == 0, result.stdout
        return result.stdout

    def calls(self):
        return self.calls_file.read_text().splitlines() if self.calls_file.is_file() else []


@pytest.fixture
def portmaster_zip():
    """What PortMaster.zip holds that the installer cares about: the real launchers."""
    files = {
        "PortMaster/pugwash": "#!/usr/bin/env python3\n",
        "PortMaster/libs/": None,
        "PortMaster/control.txt": (PM_DIR / "control.txt").read_text(),
        "PortMaster/PortMaster.sh": (PM_DIR / "PortMaster.sh").read_text(),
        }

    for cfw in ("muos", "spruce", "trimui", "retrodeck", "miyoo"):
        files[f"PortMaster/{cfw}/PortMaster.txt"] = (PM_DIR / cfw / "PortMaster.txt").read_text()
        files[f"PortMaster/{cfw}/control.txt"] = (PM_DIR / cfw / "control.txt").read_text()

    files["PortMaster/trimui/config.json"] = (PM_DIR / "trimui" / "config.json").read_text()
    files["PortMaster/trimui/icon.png"] = "png"
    files["PortMaster/batocera/control.txt"] = (PM_DIR / "batocera" / "control.txt").read_text()
    files["PortMaster/knulli/control.txt"] = (PM_DIR / "knulli" / "control.txt").read_text()
    files["PortMaster/batocera/shGenerator.py"] = "# batocera shGenerator, gamecontrollerdb.txt\n"
    files["PortMaster/knulli/shGenerator.py"] = "# knulli shGenerator, gamecontrollerdb.txt\n"
    return files


def put_zip(installer, files, name="PortMaster.zip"):
    with zipfile.ZipFile(installer.work / name, 'w') as zf:
        for file_name, data in files.items():
            info = zipfile.ZipInfo(file_name)
            ## Without modes unzip makes directories nobody can enter.
            info.external_attr = (0o40755 if data is None else 0o100644) << 16
            zf.writestr(info, data or "")


def stub(cfw=None):
    return (PM_DIR / "PortMaster.sh" if cfw is None else PM_DIR / cfw / "PortMaster.txt").read_text()


################################################################################
## Same answer as harbourmaster's detect_paths().
@pytest.mark.parametrize("cfw", sorted(CFWS))
def test_detection_matches_harbourmaster(tmp_path, cfw):
    from harbourmaster.config import detect_paths

    installer = Installer(tmp_path, cfw)
    controlfolder = installer.detect()['controlfolder']

    home = installer.path(installer.home)
    tools_dir = detect_paths(
        root=installer.root, cwd=installer.root / "somewhere",
        environ={'XDG_DATA_HOME': XDG}, home=home, df_output=lambda: "")[0]

    if str(tools_dir).startswith(str(installer.root)):
        tools_dir = tools_dir.relative_to(installer.root)

    ## Compare where they really are: ArkOS's /opt/system/Tools is /roms2/tools,
    ## ROCKNIX's /roms is /storage/roms.
    assert installer.path(controlfolder).resolve() == installer.path(tools_dir).resolve()


################################################################################
## Installing.
@pytest.fixture
def old_install():
    """A PortMaster that was already there: config, themes, runtimes, an old launcher."""
    def _old_install(installer, controlfolder):
        pm = installer.path(controlfolder) / "PortMaster"
        write(pm, "config/config.json", "{}")
        write(pm, "themes/some.theme/theme.json", "{}")
        write(pm, "libs/godot.squashfs", "runtime")
        write(pm, "PortMaster.sh", "old launcher")
        return pm

    return _old_install


def test_arkos_factory_reset(tmp_path, portmaster_zip, old_install):
    installer = Installer(tmp_path, "arkos")
    put_zip(installer, portmaster_zip)
    pm = old_install(installer, "/opt/system/Tools")
    write(installer.root, "/opt/system/Tools/PortMaster.sh", "old launcher")
    write(installer.root, "/roms2/ports/Install.PortMaster.sh", "installer")
    write(installer.root, "/roms2/ports/Restore PortMaster.sh", "restore")
    write(installer.root, "/roms2/ports/Some Game.sh", "a port")

    installer.run()

    ## Factory reset: settings and themes go, runtimes stay.
    assert not (pm / "config").exists()
    assert not (pm / "themes").exists()
    assert (pm / "libs" / "godot.squashfs").read_text() == "runtime"
    assert (pm / "pugwash").is_file()

    ## The launcher moves up to Tools/, where ES lists it.
    assert installer.path("/opt/system/Tools/PortMaster.sh").read_text() == stub()
    assert not (pm / "PortMaster.sh").exists()

    ## The installer / restore ports are gone, other ports are not.
    assert sorted(path.name for path in installer.path("/roms2/ports").iterdir()) == ["Some Game.sh"]

    assert installer.calls() == ["systemctl restart emulationstation"]


def test_unreachable_target_changes_nothing(tmp_path, portmaster_zip):
    ## If it can't get into the PortMaster directory it must not carry on from wherever
    ## it is: the next steps delete "PortMaster" and unzip over the current directory.
    installer = Installer(tmp_path, "default")
    installer.path("/roms").write_text("not a directory, so no /roms/ports")
    put_zip(installer, portmaster_zip)
    (installer.work / "PortMaster").mkdir()

    run_env = dict(installer.env, HOME=installer.home)
    result = subprocess.run(
        ["bash", str(INSTALLER)], cwd=str(installer.work), env=run_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    assert result.returncode == 1
    assert "nothing was installed" in result.stdout
    assert sorted(path.name for path in installer.work.iterdir()) == ["PortMaster", "PortMaster.zip"]
    assert installer.calls() == []


def run_failing(installer):
    run_env = dict(installer.env, HOME=installer.home)
    result = subprocess.run(
        ["bash", str(INSTALLER)], cwd=str(installer.work), env=run_env, timeout=120,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    assert result.returncode == 1, result.stdout
    assert "Finished installing" not in result.stdout
    return result.stdout


def test_broken_unzip_changes_nothing(tmp_path, portmaster_zip, old_install):
    ## spruce put an unzip needing glibc 2.34 first on PATH (TrimUI Smart Pro S, Brick):
    ## the reset deleted PortMaster, unpacked nothing, and said "Finished".
    installer = Installer(tmp_path, "arkos")
    put_zip(installer, portmaster_zip)
    pm = old_install(installer, "/opt/system/Tools")
    write_exe(tmp_path / "bin" / "unzip", 'echo "unzip: /lib/libc.so.6: version \\`GLIBC_2.34\' not found" >&2\nexit 1\n')

    output = run_failing(installer)

    assert "nothing was installed" in output
    assert "GLIBC_2.34" in output
    assert (pm / "config" / "config.json").is_file()
    assert (pm / "libs" / "godot.squashfs").read_text() == "runtime"
    assert installer.calls() == []


def test_unzip_that_unpacks_nothing(tmp_path, portmaster_zip, old_install):
    ## Reads the zip fine but extracts nothing: stop before the reboot, runtimes kept.
    installer = Installer(tmp_path, "rocknix")
    put_zip(installer, portmaster_zip)
    pm = old_install(installer, "/roms/ports")
    real_unzip = shutil.which("unzip")
    write_exe(tmp_path / "bin" / "unzip", f'[ "$1" = "-l" ] && exec "{real_unzip}" "$@"\nexit 0\n')

    output = run_failing(installer)

    assert "PortMaster is NOT installed" in output
    assert (pm / "libs" / "godot.squashfs").read_text() == "runtime"
    assert not (pm.parent / "temp_runtimes").exists()
    assert "shutdown -r now" not in installer.calls()


def test_full_installer_adds_runtimes(tmp_path, portmaster_zip):
    installer = Installer(tmp_path, "arkos")
    put_zip(installer, portmaster_zip)
    put_zip(installer, {"mono.squashfs": "mono", "godot.squashfs": "godot"}, name="runtimes.zip")

    installer.run()

    libs = installer.path("/opt/system/Tools/PortMaster/libs")
    assert sorted(path.name for path in libs.iterdir()) == ["godot.squashfs", "mono.squashfs"]


def test_no_es_restart_file(tmp_path, portmaster_zip):
    ## eg: the Restore port, or a tool installing over ssh.
    installer = Installer(tmp_path, "arkos")
    put_zip(installer, portmaster_zip)
    no_restart = write(installer.root, "/root/no_es_restart", "")

    installer.run()

    assert installer.calls() == []
    assert not no_restart.exists()


def test_muos_is_left_alone(tmp_path, portmaster_zip, old_install):
    ## muOS includes PortMaster (and a way to restore it). On releases with exfat-fuse
    ## (Banana, Jacaranda) the installer deleting itself crashes the SD card's driver,
    ## so it changes nothing at all there, itself included.
    installer = Installer(tmp_path, "muos")
    put_zip(installer, portmaster_zip)
    pm = old_install(installer, "/mnt/mmc/MUOS")
    me = write(installer.root, "/mnt/mmc/ROMS/Ports/Install.PortMaster.sh", "installer")
    before = sorted(str(path) for path in installer.root.rglob("*"))

    run_env = dict(installer.env, HOME=installer.home)
    result = subprocess.run(
        ["bash", str(INSTALLER)], cwd=str(installer.work), env=run_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    assert result.returncode == 1
    assert "muOS includes PortMaster" in result.stdout
    assert sorted(str(path) for path in installer.root.rglob("*")) == before
    assert (pm / "config" / "config.json").is_file()
    assert me.is_file()
    assert installer.calls() == []


@pytest.mark.parametrize("old_style", [False, True])
def test_batocera(tmp_path, portmaster_zip, old_style):
    installer = Installer(tmp_path, "batocera")
    put_zip(installer, portmaster_zip)
    generator = write(
        installer.root, "/usr/lib/python3.11/site-packages/configgen/generators/sh/shGenerator.py",
        "from generators.Generator import Generator\n" if old_style else "from ..Generator import Generator\n")

    installer.run()

    assert installer.path("/userdata/roms/ports/PortMaster.sh").read_text() == stub()
    assert not installer.path(XDG + "/PortMaster/PortMaster.sh").exists()
    assert installer.path(XDG + "/PortMaster/control.txt").read_text() == portmaster_zip["PortMaster/batocera/control.txt"]

    ## The system's shGenerator.py is swapped for ours, the original kept.
    expected = "knulli" if old_style else "batocera"
    assert generator.read_text().startswith(f"# {expected} shGenerator")
    assert generator.with_name("shGenerator.py.bak").is_file()
    assert installer.calls() == ["curl http://localhost:1234/reloadgames", "batocera-save-overlay "]


def test_knulli_gets_its_own_control(tmp_path, portmaster_zip):
    ## knulli is found like Batocera, but its os-release names it, and that picks
    ## knulli/control.txt over batocera's.
    portmaster_zip["PortMaster/batocera/control.txt"] = "batocera control\n"
    portmaster_zip["PortMaster/knulli/control.txt"] = "knulli control\n"
    installer = Installer(tmp_path, "batocera")
    write(installer.root, "/etc/os-release", 'NAME=Batocera.linux\nOS_NAME="knulli"\n')
    put_zip(installer, portmaster_zip)

    assert installer.detect()['OS_NAME'] == "knulli"
    installer.run()

    assert installer.path(XDG + "/PortMaster/control.txt").read_text() == "knulli control\n"
    assert installer.path("/userdata/roms/ports/PortMaster.sh").read_text() == stub()
    assert installer.calls() == ["curl http://localhost:1234/reloadgames"]


def test_batocera_patched_generator_left_alone(tmp_path, portmaster_zip):
    installer = Installer(tmp_path, "batocera")
    put_zip(installer, portmaster_zip)
    generator = write(
        installer.root, "/usr/lib/python3.11/site-packages/configgen/generators/sh/shGenerator.py",
        "# already ours, gamecontrollerdb.txt\n")

    installer.run()

    assert generator.read_text() == "# already ours, gamecontrollerdb.txt\n"
    assert not generator.with_name("shGenerator.py.bak").exists()


def test_rocknix(tmp_path, portmaster_zip):
    installer = Installer(tmp_path, "rocknix")
    put_zip(installer, portmaster_zip)

    installer.run()

    ## ROCKNIX runs PortMaster/PortMaster.sh where it is.
    assert installer.path("/storage/roms/ports/PortMaster/PortMaster.sh").read_text() == stub()
    assert installer.path("/storage/.config/PortMaster/control.txt").read_text() == "rocknix control.txt\n"
    assert installer.calls() == ["shutdown -r now"]


def test_rocknix_without_jelos_files(tmp_path, portmaster_zip):
    ## Newer ROCKNIX ships only control.txt and mapper.txt in /usr/config/PortMaster.
    installer = Installer(tmp_path, "rocknix")
    installer.path("/usr/config/PortMaster/PortMaster.sh").unlink()
    installer.path("/usr/config/PortMaster/portmaster.gptk").unlink()
    put_zip(installer, portmaster_zip)

    output = installer.run()

    assert "can't stat" not in output and "cannot stat" not in output
    assert installer.path("/storage/.config/PortMaster/control.txt").read_text() == "rocknix control.txt\n"
    assert installer.path("/storage/roms/ports/PortMaster/PortMaster.sh").read_text() == stub()


@pytest.mark.parametrize("cfw", ["retrodeck", "retrodeck_outside"])
def test_retrodeck(tmp_path, portmaster_zip, cfw):
    installer = Installer(tmp_path, cfw)
    put_zip(installer, portmaster_zip)
    write(installer.root, "/run/media/deck/sd/retrodeck/roms/portmaster/Install.PortMaster.sh", "installer")

    installer.run()

    scripts = installer.path("/run/media/deck/sd/retrodeck/roms/portmaster")
    assert sorted(path.name for path in scripts.iterdir()) == ["PortMaster.sh"]
    assert (scripts / "PortMaster.sh").read_text() == stub("retrodeck")
    ## RetroDECK can't restart ES-DE from here.
    assert installer.calls() == []


def test_spruce(tmp_path, portmaster_zip):
    installer = Installer(tmp_path, "spruce")
    put_zip(installer, portmaster_zip)

    installer.run()

    pm = installer.path("/mnt/SDCARD/Persistent/portmaster/PortMaster")
    assert (pm / "PortMaster.sh").read_text() == stub("spruce")
    assert (pm / "control.txt").read_text() == (PM_DIR / "spruce" / "control.txt").read_text()
    assert installer.calls() == []


def test_trimui(tmp_path, portmaster_zip):
    ## TrimUI bundles PortMaster (trimui.portmaster.zip), a stray run just puts it in the right place.
    installer = Installer(tmp_path, "trimui")
    put_zip(installer, portmaster_zip)

    installer.run()

    pm = installer.path("/mnt/SDCARD/Apps/PortMaster/PortMaster")
    assert (pm / "pugwash").is_file()
    assert (pm / "control.txt").read_text() == (PM_DIR / "trimui" / "control.txt").read_text()
    assert installer.calls() == []


################################################################################
## The makeself header around it.
def test_header_logs_once():
    header = (REPO_DIR / "tools" / "makeself-header.sh").read_text()
    assert header.count('tee -a "\\$HOME/portmaster.log"') == 1
