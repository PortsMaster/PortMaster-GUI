# SPDX-License-Identifier: MIT
#
# ArkOS and dArkOS.

import shutil
from loguru import logger
from .base import PlatformBase, PlatformGCD_PortMaster


class PlatformArkOS(PlatformGCD_PortMaster, PlatformBase):
    MOVE_PM_BASH = True
    ES_NAME = 'emulationstation'

    def __init__(self, hm):
        super().__init__(hm)

        # Fix a whoopsie :D
        BAD_SCRIPT  = self.hm.ports_dir / "PortMaster.sh"
        GOOD_SCRIPT = self.hm.tools_dir / "PortMaster.sh"

        if not BAD_SCRIPT.is_file():
            return

        if not GOOD_SCRIPT.is_file():
            logger.info(f"MV: {BAD_SCRIPT} -> {GOOD_SCRIPT}")
            shutil.move(BAD_SCRIPT, GOOD_SCRIPT)
            return

        if "pmsplash" not in GOOD_SCRIPT.read_text():
            logger.info(f"MV: {BAD_SCRIPT} -> {GOOD_SCRIPT}")
            shutil.move(BAD_SCRIPT, GOOD_SCRIPT)
            return

        logger.info(f"RM: {BAD_SCRIPT}")
        BAD_SCRIPT.unlink()

    def gamelist_file(self):
        return self.hm.ports_dir / 'gamelist.xml'


class PlatformdArkOS(PlatformArkOS):
    # WOO! :D
    ...
