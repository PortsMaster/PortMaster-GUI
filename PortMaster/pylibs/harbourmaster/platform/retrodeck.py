# SPDX-License-Identifier: MIT
#
# RetroDECK.

import shutil
from harbourmaster.i18n import _
from pathlib import Path
from loguru import logger
from ..util import json_safe_load, replace_file
from .base import PlatformBase


class PlatformRetroDECK(PlatformBase):
    MOVE_PM_BASH = False
    ES_NAME = 'show-refresh'
    PORTMASTER_GAMELIST = True
    RD_CONFIG = None
    ROMS_REFRESH_TEXT = _("\n\nIn order to do so:\nMENU -> UTILITIES -> Rescan Rom Directory")

    XML_ELEMENT_MAP = {
        'path': 'path',
        'name': 'name',
        'desc': 'desc',
        'releasedate': 'releasedate',
        'developer': 'developer',
        'publisher': 'publisher',
        'players': 'players',
        'genre': 'genre',
        }

    def __init__(self, hm):
        super().__init__(hm)

        self.XML_ELEMENT_CALLBACK = {
            'image': self.esde_image_copy_majigger,
            }

    def get_rdconfig(self):
        if self.RD_CONFIG is None:
            rdconfig = {}

            rdconfig['rdhome'] = None
            rdconfig['roms_folder'] = None
            rdconfig['ports_folder'] = None

            # XARGON !!!!!!
            rdconfig_file=Path("/var/config/retrodeck/retrodeck.json")
            if not rdconfig_file.is_file():
                rdconfig_file=(Path.home() / ".var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.json")

            if rdconfig_file.is_file():
                with open(rdconfig_file, 'r') as fh:
                    rdconfig_data = json_safe_load(fh)

                    if not isinstance(rdconfig_data, dict):
                        logger.error(f"Unable to load the retrodeck.json: {rdconfig_file}.")
                        return None

                    if 'rd_home_path' not in rdconfig_data.get('paths', {}):
                        logger.error(f"Unable to find the rd_home_path value in {rdconfig_file}.")
                        return None

                    rdconfig['rdhome'] = Path(rdconfig_data['paths']['rd_home_path'])

                    if 'roms_path' in rdconfig_data['paths']:
                        rdconfig['roms_folder'] = Path(rdconfig_data['paths']['roms_path'])
                    else:
                        rdconfig['roms_folder'] = rdconfig['rdhome'] / "roms"

                    if 'ports_path' in rdconfig_data['paths']:
                        rdconfig['ports_folder'] = Path(rdconfig_data['paths']['ports_path'])
                    else:
                        rdconfig['ports_folder'] = rdconfig['rdhome'] / "PortMaster"

                self.RD_CONFIG = rdconfig

                logger.info(f"RD_CONFIG: {rdconfig}")

                return self.RD_CONFIG

            rdconfig_file=Path("/var/config/retrodeck/retrodeck.cfg")
            if not rdconfig_file.is_file():
                rdconfig_file=(Path.home() / ".var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.cfg")

            if not rdconfig_file.is_file():
                logger.error("Unable to find RetroDECK's retrodeck.json or retrodeck.cfg.")
                return None

            with open(rdconfig_file, 'r') as fh:
                for line in fh:
                    line = line.strip()

                    if line.startswith('rdhome='):
                        rdconfig['rdhome'] = Path(line.split('=', 1)[-1])

                    if '_folder=' in line:
                        folder_name, folder_value = line.split('=', 1)
                        rdconfig[folder_name] = Path(folder_value)

            if rdconfig['rdhome'] is None:
                logger.error(f"Unable to find the rdhome variable in {rdconfig_file}.")
                return None

            if rdconfig['roms_folder'] is None:
                rdconfig['roms_folder'] = rdconfig['rdhome'] / "roms"

            if rdconfig['ports_folder'] is None:
                rdconfig['ports_folder'] = rdconfig['rdhome'] / "PortMaster"

            self.RD_CONFIG = rdconfig

            logger.info(f"RD_CONFIG: {rdconfig}")

        return self.RD_CONFIG

    def esde_image_copy_majigger(self, port_script, game_element, image_element):
        rdconfig = self.get_rdconfig()
        if rdconfig is None:
            return None

        IMG_DIR = rdconfig['rdhome'] / 'ES-DE' / 'downloaded_media' / 'portmaster' / 'screenshots'
        # IMG_DIR = rdconfig['rdhome'] / 'downloaded_media' / 'portmaster' / 'miximages'

        IMG_DIR.mkdir(parents=True, exist_ok=True)

        SRC_IMAGE = Path(image_element.text)
        DST_IMAGE = IMG_DIR / (Path(port_script).stem + SRC_IMAGE.suffix)

        if not SRC_IMAGE.is_file():
            logger.warning(f"{port_script}: no image at {SRC_IMAGE}")
            return

        logger.info(f"COPY: {SRC_IMAGE} -> {DST_IMAGE}")
        shutil.copy(SRC_IMAGE, DST_IMAGE)

    def gamelist_file(self):
        rdconfig = self.get_rdconfig()
        if rdconfig is None:
            return None

        gamelists_dir = rdconfig['rdhome'] / 'ES-DE' / 'gamelists' / 'portmaster'

        gamelists_dir.mkdir(parents=True, exist_ok=True)

        return gamelists_dir / 'gamelist.xml'

    def first_run(self):
        self.portmaster_install([])

    def portmaster_install(self, bash_files):
        """
        Move files into place.
        """
        super().portmaster_install(bash_files)

        RD_DIR = self.hm.tools_dir / "PortMaster" / "retrodeck"
        PM_DIR = self.hm.tools_dir / "PortMaster"
        SC_DIR = self.hm.scripts_dir

        # ACTIVATE THE RetroDECK CONTROL
        logger.debug(f'Copy {RD_DIR / "control.txt"} -> {PM_DIR / "control.txt"}')
        shutil.copy(RD_DIR / "control.txt", PM_DIR / "control.txt")

        # PEBKAC RD
        logger.debug(f'Move {RD_DIR / "PortMaster.txt"} -> {PM_DIR / "PortMaster.sh"}')
        replace_file(RD_DIR / "PortMaster.txt", PM_DIR / "PortMaster.sh")

        logger.debug(f'Move {RD_DIR / "PortMaster.txt"} -> {SC_DIR / "PortMaster.sh"}')
        if (SC_DIR / "PortMaster.sh").is_symlink():
            # XARGONNNNNNNN
            (SC_DIR / "PortMaster.sh").unlink()

        replace_file(RD_DIR / "PortMaster.txt", SC_DIR / "PortMaster.sh")

        # Fix perms
        bash_files.append(SC_DIR / "PortMaster.sh")

        TASK_SET = Path(self.hm.tools_dir / "PortMaster" / "tasksetter")
        if TASK_SET.is_file():
            TASK_SET.unlink()

        TASK_SET.touch()
