# SPDX-License-Identifier: MIT
#
# muOS.

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from loguru import logger
from ..util import replace_file
from .base import PlatformBase, SPECIAL_GAMELIST_CODE


class PlatformmuOS(PlatformBase):
    MOVE_PM_BASH = False
    ES_NAME = "muos"

    XML_ELEMENT_MAP = {
        'image': 'image',
        'desc': 'desc',
        }

    MUOSAPP_PM_MARKER = ".portmaster_was_here.txt"

    def gamelist_file(self):
        return SPECIAL_GAMELIST_CODE

    def gamelist_add(self, gameinfo_file):
        # Xonglebongle: the sound of someone sneezing while trying to pronounce 'jungle' underwater.
        if not gameinfo_file.is_file():
            return

        if not any((
                Path("/opt/graphicsmagick").is_dir(),
                Path("/usr/bin/magick").is_file())):
            return

        INFO_CATALOG = Path("/run/muos/storage/info/catalogue/External - Ports")
        if not INFO_CATALOG.exists():
            INFO_CATALOG = Path("/mnt/mmc/MUOS/info/catalogue/External - Ports")

        INFO_BOX_DIR     = INFO_CATALOG / "box"
        INFO_PREVIEW_DIR = INFO_CATALOG / "preview"
        INFO_TEXT_DIR    = INFO_CATALOG / "text"

        ## Not this muOS's layout: leave it be.
        if not INFO_CATALOG.is_dir():
            return

        for info_dir in (INFO_BOX_DIR, INFO_PREVIEW_DIR, INFO_TEXT_DIR):
            info_dir.mkdir(exist_ok=True)

        with self.gamelist_backup() as gamelist_xml:
            if gamelist_xml is None:
                return

            gameinfo_tree = ET.parse(gameinfo_file)
            gameinfo_root = gameinfo_tree.getroot()

            for gameinfo_element in gameinfo_tree.findall('game'):
                path_merge = gameinfo_element.find('path').text

                if path_merge.startswith('./'):
                    path_merge = path_merge[2:]

                path_merge = path_merge.rsplit('.', 1)[0]

                for child in gameinfo_element:
                    # Check if the child element is in the predefined list
                    if child.tag not in self.XML_ELEMENT_MAP:
                        continue

                    # logger.warning(f"{child.tag}: {child.text}")

                    if child.tag == 'image':
                        text = child.text

                        if text.startswith('./'):
                            text = text[2:]

                        image_file = self.hm.ports_dir / text
                        if not image_file.is_file():
                            continue

                        target_file = INFO_BOX_DIR / (path_merge + '-pre' + image_file.suffix)
                        logger.debug(f"copying {str(image_file)} to {str(target_file)}")
                        shutil.copy(image_file, target_file)

                        screenshot_file = None
                        if (image_file.parent / 'screenshot.jpg').is_file():
                            screenshot_file = (image_file.parent / 'screenshot.jpg')

                        elif (image_file.parent / 'screenshot.png').is_file():
                            screenshot_file = (image_file.parent / 'screenshot.png')

                        if screenshot_file:
                            target_file = INFO_PREVIEW_DIR / (path_merge + '-pre' + image_file.suffix)
                            logger.debug(f"copying {str(screenshot_file)} to {str(target_file)}")
                            shutil.copy(screenshot_file, target_file)

                    elif child.tag == 'desc':
                        target_file = INFO_TEXT_DIR / (path_merge + '.txt')
                        text = child.text.strip().split('\n', 1)[0].strip()

                        logger.debug(f"creating {str(target_file)}")
                        with open(target_file, 'w') as fh:
                            print(text, file=fh)

            # HAHA THIS IS FUCKED
            self.added_ports.add('GAMELIST UPDATER')

    def first_run(self):
        self.portmaster_install([])

    def port_install(self, port_name, port_info, port_files, fix_perm_files):
        super().port_install(port_name, port_info, port_files, fix_perm_files)

        logger.debug(f"{self.__class__.__name__}: Port Install {port_name}")
        logger.debug(f"--------------------- muOS platform port_install -----------------------------------")

        """
        Install port to application folder if mux_launch.sh exists
        """

        PORT_FOLDER = port_info['files']['port.json'].split('/', 1)[0]

        # Safe default.
        APP_NAME = port_info['name'].rsplit('.', 1)[0]
        for port_file in port_info['files']:
            if port_file.lower().endswith('.sh'):
                # Use the first bash script we find.
                APP_NAME = port_file.rsplit('.', 1)[0]
                break

        MUOSAPP_DIR     = Path("/run/muos/storage/application")
        MUOSAPP_APP_DIR = MUOSAPP_DIR / APP_NAME
        MUX_FILE_PATH   = self.hm.ports_dir / PORT_FOLDER / "mux_launch.txt"

        logger.debug(f"mux app file path being checked: {MUX_FILE_PATH}")
        logger.debug(f"Destination directory: {MUOSAPP_APP_DIR}")
        logger.debug("-" * 20)

        if MUOSAPP_DIR.is_dir() and MUX_FILE_PATH.is_file():
            # File found, proceed with copy operations
            logger.debug(f"Port is an Application: copying launch script to {MUOSAPP_APP_DIR}")
            
            try:
                MUOSAPP_APP_DIR.mkdir(exist_ok=True)
                logger.debug(f"Created destination directory: {MUOSAPP_APP_DIR}")
                shutil.copy2(MUX_FILE_PATH, MUOSAPP_APP_DIR / "mux_launch.sh")
                logger.debug("Copy successful.")

                with (MUOSAPP_APP_DIR / self.MUOSAPP_PM_MARKER).open("w") as fh:
                    fh.write(APP_NAME)

            except OSError as e:
                logger.error(f"Error during file operation: {e}")

        else:
            # mux_launch.sh File not found
            logger.debug(f"port is not an application, no mux_launch.txt")

    def port_uninstall(self, port_name, port_info, port_files):
        super().port_uninstall(port_name, port_info, port_files)

        logger.debug(f"{self.__class__.__name__}: Port Uninstall {port_name}")
        logger.debug(f"--------------------- muOS platform port_uninstall -----------------------------------")

        """
        Remove port application folder if PM_MARKER exists in  `/run/muos/storage/application/{Port Script Name}/`
        """

        PORT_FOLDER = port_info['files']['port.json'].split('/', 1)[0]

        # Safe default.
        APP_NAME = port_info['name'].rsplit('.', 1)[0]
        for port_file in port_info['files']:
            if port_file.lower().endswith('.sh'):
                # Use the first bash script we find.
                APP_NAME = port_file.rsplit('.', 1)[0]
                break

        MUOSAPP_DIR     = Path("/run/muos/storage/application")
        MUOSAPP_APP_DIR = MUOSAPP_DIR / APP_NAME

        logger.debug(f"Destination directory: {MUOSAPP_APP_DIR}")
        logger.debug("-" * 20)

        if MUOSAPP_APP_DIR.is_dir() and (MUOSAPP_APP_DIR / self.MUOSAPP_PM_MARKER).is_file():
            # File found, proceed with copy operations
            logger.debug(f"Port had an Application: removing app directory {MUOSAPP_APP_DIR}")
            
            try:
                shutil.rmtree(MUOSAPP_APP_DIR)

            except OSError as e:
                logger.debug(f"Error during file operation: {e}")

    def portmaster_install(self, bash_files):
        """
        Move files into place.
        """
        super().portmaster_install(bash_files)

        MU_DIR = self.hm.tools_dir / "PortMaster" / "muos"
        PM_DIR = self.hm.tools_dir / "PortMaster"

        # ACTIVATE THE CONTROL
        logger.debug(f'Copy {MU_DIR / "control.txt"} -> {PM_DIR / "control.txt"}')
        shutil.copy(MU_DIR / "control.txt", PM_DIR / "control.txt")

        CONTROL_HACK = Path("/roms/ports/PortMaster/control.txt")
        if not CONTROL_HACK.parent.is_dir():
            CONTROL_HACK.parent.mkdir(parents=True)

        logger.debug(f'Copy {MU_DIR / "control.txt"} -> {CONTROL_HACK}')
        shutil.copy(MU_DIR / "control.txt", CONTROL_HACK)

        # PEBKAC
        logger.debug(f'Move {MU_DIR / "PortMaster.txt"} -> {PM_DIR / "PortMaster.sh"}')
        replace_file(MU_DIR / "PortMaster.txt", PM_DIR / "PortMaster.sh")

        bash_files.append(PM_DIR / "PortMaster.sh")

        TASK_SET = Path(self.hm.tools_dir / "PortMaster" / "tasksetter")
        if TASK_SET.is_file():
            TASK_SET.unlink()

        TASK_SET.touch()
