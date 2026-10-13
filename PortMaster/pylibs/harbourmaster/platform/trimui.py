# SPDX-License-Identifier: MIT
#
# TrimUI stock firmware.

import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from loguru import logger
from ..util import name_cleaner, replace_file
from .base import PlatformBase, SPECIAL_GAMELIST_CODE


PORT_CONFIG_JSON = """
{
    "package":"{{PORTNAME}}",
    "label":"{{PORTTITLE}}",
    "icon":"icon.png",
    "themecolor":"61A8DD",
    "launch":"{{PORTSCRIPT}}",
    "description":"A Port"
}
"""

class PlatformTrimUI(PlatformBase):
    WANT_XBOX_FIX = True
    ES_NAME = "trimui"

    XML_ELEMENT_MAP = {
        'image': 'image',
        }

    def first_run(self):
        self.portmaster_install([])

    def portmaster_install(self, bash_files):
        """
        Move files into place.
        """
        super().portmaster_install(bash_files)

        TU_DIR = self.hm.tools_dir / "PortMaster" / "trimui"
        PM_DIR = self.hm.tools_dir / "PortMaster"

        # ACTIVATE THE CONTROL
        logger.debug(f'Copy {TU_DIR / "control.txt"} -> {PM_DIR / "control.txt"}')
        shutil.copy(TU_DIR / "control.txt", PM_DIR / "control.txt")

        CONTROL_HACK = Path("/roms/ports/PortMaster/control.txt")
        if not CONTROL_HACK.parent.is_dir():
            CONTROL_HACK.parent.mkdir(parents=True)

        logger.debug(f'Copy {TU_DIR / "control.txt"} -> {CONTROL_HACK}')
        shutil.copy(TU_DIR / "control.txt", CONTROL_HACK)

        # PEBKAC
        logger.debug(f'Move {TU_DIR / "PortMaster.txt"} -> {self.hm.tools_dir / "launch.sh"}')
        replace_file(TU_DIR / "PortMaster.txt", self.hm.tools_dir / "launch.sh")

        bash_files.append(self.hm.tools_dir / "launch.sh")

        TASK_SET = Path(PM_DIR / "tasksetter")
        if TASK_SET.is_file():
            TASK_SET.unlink()

        TASK_SET.touch()

    def port_install(self, port_name, port_info, port_files, fix_perm_files):
        super().port_install(port_name, port_info, port_files, fix_perm_files)

        ## Gets called when a port is installed.
        # logger.debug(f"{port_name}: {port_files}")

        scripts_dir = '/'.join(self.hm.scripts_dir.parts)
        scripts_dir_parts = len(self.hm.scripts_dir.parts)

        for port_file in port_files:
            if not port_file.name.lower().endswith('.sh'):
                continue

            if len(port_file.parts) != (scripts_dir_parts+1):
                logger.debug(f"{len(port_file.parts)} != {(scripts_dir_parts+1)}")
                continue

            if scripts_dir != '/'.join(port_file.parts[:scripts_dir_parts]):
                logger.debug(f"{scripts_dir} != {str(port_file)}")
                continue

            self.add_port_script(port_file)
            # I should add to fix_perm_files, but fucking TrimUI... i doubt it is using ext4. :D

    def port_uninstall(self, port_name, port_info, port_files):
        super().port_uninstall(port_name, port_info, port_files)
        # logger.debug(f"{port_name}: {port_files}")

        for port_file in port_files:
            if port_file.endswith('.sh'):
                self.remove_port_script(self.hm.scripts_dir / port_file)

    def add_port_script(self, port_script):
        ROM_SCRIPT_DIR = Path("/mnt/SDCARD/Roms/PORTS")
        PORT_DIR       = Path("/mnt/SDCARD/Ports")

        port_mode = self.hm.cfg_data.get('trimui-port-mode', 'roms')

        if port_mode == 'roms':
            target_file = ROM_SCRIPT_DIR / (port_script.name)
            if not target_file.exists() or not os.path.samefile(port_script, target_file):
                logger.debug(f"Copying {str(port_script)} to {str(target_file)}")
                shutil.copy(port_script, target_file)
            else:
                logger.debug(f"Skipping copy of {str(port_script)} to {str(target_file)} as they are the same file")

        elif port_mode == 'ports':
            new_port_dir = PORT_DIR / f"portmaster-{name_cleaner(port_script.stem)}"

            new_port_dir.mkdir(0o755, parents=True, exist_ok=True)

            logger.debug(f"Creating {str(new_port_dir / 'config.json')}")
            with open(new_port_dir / "config.json", "w") as fh:
                fh.write(
                    PORT_CONFIG_JSON
                    .replace("{{PORTTITLE}}", port_script.stem)
                    .replace("{{PORTNAME}}", new_port_dir.name.lower())
                    ## A-PEH ESC-A-PEH
                    .replace("{{PORTSCRIPT}}", str(port_script).replace(' ', '\\\\ ')))

    def remove_port_script(self, port_script):
        ROM_SCRIPT_DIR = Path("/mnt/SDCARD/Roms/PORTS")
        PORT_DIR       = Path("/mnt/SDCARD/Ports")

        rom_script = (ROM_SCRIPT_DIR / port_script.name)
        if rom_script.is_file():
            logger.info(f"Removing: {str(rom_script)}")
            rom_script.unlink()

        port_dir = (PORT_DIR / f"portmaster-{name_cleaner(port_script.stem)}")
        if port_dir.is_dir():
            logger.info(f"Removing: {str(port_dir)}")
            shutil.rmtree(port_dir)

    def do_move_ports(self):
        port_mode = self.hm.cfg_data.get('trimui-port-mode', 'roms')

        ROM_IMAGE_DIR  = Path("/mnt/SDCARD/Imgs/PORTS")
        ROM_SCRIPT_DIR = Path("/mnt/SDCARD/Roms/PORTS")
        PORT_DIR       = Path("/mnt/SDCARD/Ports")

        if port_mode == 'roms':
            ## Delete port apps.
            for port_dir in PORT_DIR.glob('portmaster-*'):
                if not port_dir.is_dir():
                    continue

                shutil.rmtree(port_dir)

        elif port_mode == 'ports':
            ## Delete ports scripts.
            for port_file in ROM_SCRIPT_DIR.glob('*.sh'):
                if not port_file.is_file():
                    continue

                port_file.unlink()

        for port_script in self.hm.ports_dir.iterdir():
            # Do scripts
            if not port_script.is_file():
                continue

            self.add_port_script(port_script)

        for port_dir in self.hm.ports_dir.iterdir():
            # Fill it out with gameinfo if available.
            if not port_dir.is_dir():
                continue

            gameinfo_file = port_dir / 'gameinfo.xml'

            if not gameinfo_file.is_file():
                continue

            self.gamelist_add(gameinfo_file)

    def gamelist_file(self):
        return SPECIAL_GAMELIST_CODE

    def gamelist_add(self, gameinfo_file):
        if not gameinfo_file.is_file():
            return

        port_mode = self.hm.cfg_data.get('trimui-port-mode', 'roms')

        ROM_IMAGE_DIR  = Path("/mnt/SDCARD/Imgs/PORTS")
        ROM_SCRIPT_DIR = Path("/mnt/SDCARD/Roms/PORTS")
        PORT_DIR       = Path("/mnt/SDCARD/Ports")

        logger.debug(f"Processing {gameinfo_file}")

        self.added_ports.add('GAMELIST UPDATER')

        with self.gamelist_backup() as gamelist_xml:
            if gamelist_xml is None:
                return

            gameinfo_tree = ET.parse(gameinfo_file)
            gameinfo_root = gameinfo_tree.getroot()

            for gameinfo_element in gameinfo_tree.findall('game'):
                port_script = gameinfo_element.find('path').text

                port_script_file = self.hm.scripts_dir / port_script

                if not port_script_file.is_file():
                    logger.debug(f"Cant find {port_script}")
                    continue

                if port_script.startswith('./'):
                    port_script = port_script[2:]

                port_title = gameinfo_element.find('name')
                if port_title is None:
                    logger.debug(f"Cant find name tag for {port_script}")
                    port_title = port_script_file.stem
                else:
                    port_title = port_title.text.strip()

                port_image = gameinfo_element.find('image')
                if port_image is not None:
                    port_image = port_image.text.strip()
                    if port_image.startswith('./'):
                        port_image = port_image[2:]

                    image_file = self.hm.ports_dir / port_image
                    if not image_file.is_file():
                        logger.debug(f"Cant find image file {image_file}")
                        image_file = None

                    logger.info(f"{port_image}: {image_file}")
                else:
                    logger.debug(f"Cant find image tag.")
                    image_file = None

                logger.debug(f"{port_mode} -- {image_file}")

                if port_mode == 'roms':
                    if image_file is not None:
                        target_file = ROM_IMAGE_DIR / (port_script_file.stem + "-pre" + image_file.suffix)
                        logger.debug(f"Copying {str(image_file)} to {str(target_file)}")
                        shutil.copy(image_file, target_file)

                    target_file = ROM_SCRIPT_DIR / (port_script_file.name)
                    logger.debug(f"Copying {str(port_script_file)} to {str(target_file)}")
                    shutil.copy(port_script_file, target_file)

                elif port_mode == 'ports':
                    new_port_dir = PORT_DIR / f"portmaster-{name_cleaner(port_script_file.stem)}"

                    new_port_dir.mkdir(0o755, parents=True, exist_ok=True)

                    logger.debug(f"Creating {str(new_port_dir / 'config.json')}")
                    with open(new_port_dir / "config.json", "w") as fh:
                        fh.write(
                            PORT_CONFIG_JSON
                            .replace("{{PORTTITLE}}", port_title)
                            .replace("{{PORTNAME}}", new_port_dir.name.lower())
                            ## A-PEH ESC-A-PEH
                            .replace("{{PORTSCRIPT}}", str(port_script_file).replace(' ', '\\\\ ')))

                    if image_file is not None:
                        target_file = new_port_dir / ("icon-pre" + image_file.suffix)
                        logger.debug(f"Copying {str(image_file)} to {str(target_file)}")
                        shutil.copy(image_file, target_file)
