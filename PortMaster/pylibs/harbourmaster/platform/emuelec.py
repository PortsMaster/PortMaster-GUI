# SPDX-License-Identifier: MIT
#
# EmuELEC, AmberELEC and UnofficialOS.

import os
from pathlib import Path
from .base import PlatformBase, PlatformGCD_PortMaster


class PlatformUOS(PlatformGCD_PortMaster, PlatformBase):
    ES_NAME = os.environ.get("UI_SERVICE","emustation").split()[0].replace(".service", "")

    def gamelist_file(self):
        return self.hm.ports_dir / 'gamelist.xml'


class PlatformAmberELEC(PlatformGCD_PortMaster, PlatformBase):
    MOVE_PM_BASH = True
    ES_NAME = 'emustation'
    PORTMASTER_GAMELIST = True

    def gamelist_file(self):
        return self.hm.ports_dir / 'gamelist.xml'


class PlatformEmuELEC(PlatformGCD_PortMaster, PlatformBase):
    MOVE_PM_BASH = True
    MOVE_PM_BASH_DIR = Path("/emuelec/scripts/")
    ES_NAME = 'emustation'

    def gamelist_file(self):
        return self.hm.scripts_dir / 'gamelist.xml'
