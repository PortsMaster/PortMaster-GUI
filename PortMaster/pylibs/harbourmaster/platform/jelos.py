# SPDX-License-Identifier: MIT
#
# JELOS and ROCKNIX.

import shutil
from pathlib import Path
from .base import PlatformBase


class PlatformJELOS(PlatformBase):
    ES_NAME = 'emustation'

    def gamelist_file(self):
        return self.hm.ports_dir / 'gamelist.xml'

    def first_run(self):
        self.portmaster_install([])

    def portmaster_install(self, bash_files):
        """
        Copy JELOS PortMaster files here.
        """

        ## Copy the JELOS portmaster stuff into the right place.
        JELOS_PM_DIR = Path("/storage/.config/PortMaster")
        PM_DIR = self.hm.tools_dir / "PortMaster"

        if not JELOS_PM_DIR.is_dir():
            shutil.copytree("/usr/config/PortMaster", JELOS_PM_DIR)

        ## Copy the files as per usual.
        shutil.copy(JELOS_PM_DIR / "control.txt", PM_DIR / "control.txt")
        # shutil.copy(JELOS_PM_DIR / "gptokeyb", PM_DIR / "gptokeyb")
        shutil.copy(JELOS_PM_DIR / "gamecontrollerdb.txt", PM_DIR / "gamecontrollerdb.txt")
        shutil.copy(JELOS_PM_DIR / "mapper.txt", PM_DIR / "mapper.txt")

        for oga_control in JELOS_PM_DIR.glob("oga_controls*"):
            shutil.copy(oga_control, PM_DIR / oga_control.name)


class PlatformROCKNIX(PlatformJELOS):
    ES_NAME = 'weston'
