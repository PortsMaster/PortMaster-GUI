# SPDX-License-Identifier: MIT
#
# Platform hooks run when PortMaster.zip is installed / first launched afterwards.

import pytest

from harbourmaster.platform.batocera import PlatformBatocera, PlatformKnulli, PlatformREGLinux


STUB = "#!/bin/bash\nsource \"$controlfolder/utils/pm_launch.txt\"\n"


@pytest.fixture
def batocera_dirs(hm, tmp_path, monkeypatch):
    """Batocera / knulli: tools in ~/.local/share, the launcher lives in /userdata/roms/ports."""
    tools_dir = tmp_path / "share"
    scripts_dir = tmp_path / "roms" / "ports"
    pm_dir = tools_dir / "PortMaster"

    for cfw in ("batocera", "knulli"):
        (pm_dir / cfw).mkdir(parents=True)
        (pm_dir / cfw / "control.txt").write_text(f"# {cfw} control\n")

    (pm_dir / "PortMaster.sh").write_text(STUB)
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "PortMaster.sh").write_text("# the old launcher\n")

    monkeypatch.setattr(hm, "tools_dir", tools_dir)
    monkeypatch.setattr(hm, "scripts_dir", scripts_dir)
    return pm_dir, scripts_dir


@pytest.mark.parametrize("platform_class, cfw", [
    (PlatformBatocera, "batocera"),
    (PlatformREGLinux, "batocera"),
    (PlatformKnulli, "knulli"),
    ])
def test_batocera_install_moves_launcher(hm, batocera_dirs, platform_class, cfw):
    pm_dir, scripts_dir = batocera_dirs

    platform_class(hm).portmaster_install([])

    ## The new launcher replaces the one the frontend runs.
    assert (scripts_dir / "PortMaster.sh").read_text() == STUB
    assert not (pm_dir / "PortMaster.sh").exists()
    assert (pm_dir / "control.txt").read_text() == f"# {cfw} control\n"
    assert (pm_dir / "tasksetter").is_file()


@pytest.mark.parametrize("old_location", ["PortMaster/PortMaster.sh", "PortMaster.sh"])
def test_batocera_post_install_moves_launcher(hm, batocera_dirs, old_location):
    ## The update was installed by an older harbourmaster that left the launcher behind.
    pm_dir, scripts_dir = batocera_dirs
    (pm_dir / "PortMaster.sh").unlink()
    (pm_dir.parent / old_location).write_text(STUB)

    PlatformKnulli(hm).portmaster_post_install()

    assert (scripts_dir / "PortMaster.sh").read_text() == STUB
    assert not (pm_dir.parent / old_location).exists()


def test_batocera_post_install_nothing_to_move(hm, batocera_dirs):
    pm_dir, scripts_dir = batocera_dirs
    (pm_dir / "PortMaster.sh").unlink()

    PlatformKnulli(hm).portmaster_post_install()

    assert (scripts_dir / "PortMaster.sh").read_text() == "# the old launcher\n"
