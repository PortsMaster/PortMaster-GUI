# SPDX-License-Identifier: MIT
#
# Miyoo and spruceOS.

import os
import shutil
from pathlib import Path
from loguru import logger
from ..util import replace_file
from .base import PlatformBase


class PlatformMiyoo(PlatformBase):
    WANT_XBOX_FIX = True

    def first_run(self):
        self.portmaster_install([])

    def portmaster_install(self, bash_files):
        """
        Move files into place.
        """
        super().portmaster_install(bash_files)

        MY_DIR = self.hm.tools_dir / "PortMaster" / "miyoo"
        PM_DIR = self.hm.tools_dir / "PortMaster"

        # ACTIVATE THE CONTROL
        logger.debug(f'Copy {MY_DIR / "control.txt"} -> {PM_DIR / "control.txt"}')
        shutil.copy(MY_DIR / "control.txt", PM_DIR / "control.txt")

        # ACTIVATE THE PORTMASTER
        logger.debug(f'Copy {MY_DIR / "PortMaster.txt"} -> {PM_DIR / "PortMaster.sh"}')
        replace_file(MY_DIR / "PortMaster.txt", PM_DIR / "PortMaster.sh")

        bash_files.append(PM_DIR / "PortMaster.sh")

        # CONTROL HACK
        CONTROL_HACK = Path("/root/.local/share/PortMaster/control.txt")
        if not CONTROL_HACK.parent.is_dir():
            CONTROL_HACK.parent.mkdir(parents=True)

        logger.debug(f'Copy {MY_DIR / "control.txt"} -> {CONTROL_HACK}')
        shutil.copy(MY_DIR / "control.txt", CONTROL_HACK)


class PlatformSpruce(PlatformBase):
    WANT_XBOX_FIX = True

    def first_run(self):
        self.portmaster_install([])

    def portmaster_install(self, bash_files):
        """
        Move files into place.
        """
        super().portmaster_install(bash_files)

        SP_DIR = self.hm.tools_dir / "PortMaster" / "spruce"
        PM_DIR = self.hm.tools_dir / "PortMaster"

        logger.debug(f'Copy {SP_DIR / "control.txt"} -> {PM_DIR / "control.txt"}')
        shutil.copy(SP_DIR / "control.txt", PM_DIR / "control.txt")

        logger.debug(f'Copy {SP_DIR / "PortMaster.txt"} -> {PM_DIR / "PortMaster.sh"}')
        replace_file(SP_DIR / "PortMaster.txt", PM_DIR / "PortMaster.sh")

        bash_files.append(PM_DIR / "PortMaster.sh")

        XDG_DATA_HOME = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
        CONTROL_HACK = XDG_DATA_HOME / "PortMaster" / "control.txt"
        CONTROL_HACK.parent.mkdir(parents=True, exist_ok=True)

        logger.debug(f'Copy {SP_DIR / "control.txt"} -> {CONTROL_HACK}')
        shutil.copy(SP_DIR / "control.txt", CONTROL_HACK)

    def portmaster_post_install(self):
        self.portmaster_install([])
