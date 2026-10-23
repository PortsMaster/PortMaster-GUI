# SPDX-License-Identifier: MIT
#
# PlatformBase: the hooks HarbourMaster calls, plus shared helpers.

import contextlib
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from loguru import logger
from ..util import CancelEvent


SPECIAL_GAMELIST_CODE = object()

class PlatformBase():
    WANT_XBOX_FIX = False
    WANT_SWAP_BUTTONS = False

    MOVE_PM_BASH = False
    MOVE_PM_BASH_DIR = None
    ES_NAME = None
    ROMS_REFRESH_TEXT = ""

    XML_ELEMENT_MAP = {
        'path': 'path',
        'name': 'name',
        'image': 'image',
        'desc': 'desc',
        'releasedate': 'releasedate',
        'developer': 'developer',
        'publisher': 'publisher',
        'players': 'players',
        'genre': 'genre',
        }

    XML_ELEMENT_CALLBACK = {
        }

    XML_PATH_FIX = [
        'image',
        ]

    BLANK_GAMELIST_XML = """<?xml version='1.0' encoding='utf-8'?>\n<gameList />\n"""

    ## The launcher is in this frontend's ports list, so PortMaster adds its own entry
    ## (PortMaster/gameinfo.xml) to the gamelist.
    PORTMASTER_GAMELIST = False

    def __init__(self, hm):
        self.hm = hm
        self.added_ports = set()
        self.removed_ports = set()

    def loaded(self):
        ...

    def do_move_ports(self):
        ...

    def gamelist_file(self):
        return None

    @contextlib.contextmanager
    def gamelist_backup(self):
        if not hasattr(self, '_GAMELIST_BACKUP'):
            self._GAMELIST_BACKUP = 0

        gamelist_xml = self.gamelist_file()

        if gamelist_xml is None:
            yield gamelist_xml
            return

        if gamelist_xml is SPECIAL_GAMELIST_CODE:
            ## The CFW's own catalogue (muOS, TrimUI): nothing to back up, but a failure
            ## mustn't fail the install either.
            try:
                yield gamelist_xml

            except BaseException as err:
                if isinstance(err, (CancelEvent, KeyboardInterrupt, SystemExit, GeneratorExit)):
                    raise

                logger.exception(f"Updating the frontend's catalogue failed: {err}")

            return

        gamelist_bak = gamelist_xml.with_name(gamelist_xml.name + '.bak')

        broken = False
        if not gamelist_xml.is_file():
            if gamelist_bak.is_file():
                logger.debug(f"Restore {gamelist_bak} to {gamelist_xml}")
                shutil.copy(gamelist_bak, gamelist_xml)

            else:
                broken = True

        elif gamelist_xml.is_file() and gamelist_xml.stat().st_size == 0:
            if gamelist_bak.is_file():
                logger.debug(f"Restore {gamelist_bak} to {gamelist_xml}")
                shutil.copy(gamelist_bak, gamelist_xml)

            else:
                broken = True

        if broken:
            logger.debug(f"Creating empty {gamelist_xml}")
            with open(gamelist_xml, 'w') as fh:
                print(self.BLANK_GAMELIST_XML, file=fh)

        try:
            if self._GAMELIST_BACKUP == 0:
                logger.debug(f"Backing up {gamelist_xml} to {gamelist_bak}")
                shutil.copy(gamelist_xml, gamelist_bak)

            self._GAMELIST_BACKUP += 1

            yield gamelist_xml

        except BaseException as err:
            if self._GAMELIST_BACKUP == 1:
                logger.debug(f"Restoring {gamelist_bak} to {gamelist_xml}")
                shutil.copy(gamelist_bak, gamelist_xml)

            ## Cancelling / quitting goes on up. Anything else is logged and dropped,
            ## a broken gamelist must never fail the install that updates it.
            if isinstance(err, (CancelEvent, KeyboardInterrupt, SystemExit, GeneratorExit)):
                raise

            logger.exception(f"Updating {gamelist_xml} failed, restored the backup: {err}")

        finally:
            self._GAMELIST_BACKUP -= 1

    def gamelist_add(self, gameinfo_file):
        if not gameinfo_file.is_file():
            return

        FIX_PATH = self.hm.ports_dir != self.hm.scripts_dir

        with self.gamelist_backup() as gamelist_xml:
            if gamelist_xml is None:
                return

            gamelist_tree = ET.parse(gamelist_xml)
            gamelist_root = gamelist_tree.getroot()

            gameinfo_tree = ET.parse(gameinfo_file)
            gameinfo_root = gameinfo_tree.getroot()

            for gameinfo_element in gameinfo_tree.findall('game'):
                path_merge = gameinfo_element.find('path').text

                gamelist_update = gamelist_root.find(f'.//game[path="{path_merge}"]')
                if gamelist_update is None:
                    # Create a new game element
                    gamelist_update = ET.SubElement(gamelist_root, 'game')

                logger.info(f'{path_merge}: ')

                for child in gameinfo_element:
                    # Check if the child element is in the predefined list
                    if child.tag in self.XML_ELEMENT_MAP:
                        gamelist_element = gamelist_update.find(self.XML_ELEMENT_MAP[child.tag])

                        if gamelist_element is None:
                            gamelist_element = ET.SubElement(gamelist_update, self.XML_ELEMENT_MAP[child.tag])

                        if FIX_PATH and child.tag in self.XML_PATH_FIX:
                            new_path = child.text.strip()
                            if new_path.startswith('./'):
                                new_path = new_path[2:]

                            gamelist_element.text = str(self.hm.ports_dir / new_path)

                        else:
                            gamelist_element.text = child.text

                for child in gameinfo_element:
                    if child.tag in self.XML_ELEMENT_CALLBACK:
                        ## Callbacks (eg: copying the image) get a real path, not one relative to the ports dir.
                        if child.tag in self.XML_PATH_FIX:
                            new_path = child.text.strip()
                            if new_path.startswith('./'):
                                new_path = new_path[2:]

                            child.text = str(self.hm.ports_dir / new_path)

                        self.XML_ELEMENT_CALLBACK[child.tag](path_merge, gamelist_update, child)

            if hasattr(ET, 'indent'):
                ET.indent(gamelist_root, space="  ", level=0)

            with open(gamelist_xml, 'w') as fh:
                print("<?xml version='1.0' encoding='utf-8'?>", file=fh)
                print("", file=fh)
                print(ET.tostring(gamelist_root, encoding='unicode'), file=fh)

            self.added_ports.add('GAMELIST UPDATER')

    def ports_changed(self):
        return (len(self.added_ports) > 0 or len(self.removed_ports) > 0)

    def first_run(self):
        """
        Called on first run, this can be used to add custom sources for your platform.
        """
        logger.debug(f"{self.__class__.__name__}: First Run")

    def port_install(self, port_name, port_info, port_files, fix_perm_files):
        """
        Called on after a port is installed, this can be used to check permissions, possibly augment the bash scripts.
        """
        logger.debug(f"{self.__class__.__name__}: Port Install {port_name}")

        if port_name in self.removed_ports:
            self.removed_ports.remove(port_name)
        else:
            self.added_ports.add(port_name)

    def runtime_install(self, runtime_name, runtime_files):
        """
        Called on after a port is installed, this can be used to check permissions, possibly augment the bash scripts.
        """
        logger.debug(f"{self.__class__.__name__}: Runtime Install {runtime_name}")

    def port_uninstall(self, port_name, port_info, port_files):
        """
        Called on after a port is uninstalled, this can be used clean up special files.
        """
        logger.debug(f"{self.__class__.__name__}: Port Uninstall {port_name}")

        if port_name in self.added_ports:
            self.added_ports.remove(port_name)
        else:
            self.removed_ports.add(port_name)

    def portmaster_install(self, bash_files):
        """
        Called on after portmaster is updated, this can be used clean up special files.
        """
        logger.debug(f"{self.__class__.__name__}: PortMaster Install")

    def portmaster_post_install(self):
        """
        Called on after portmaster is updated, on next launch, this can be used clean up special files, fix up boo boos.
        """
        logger.debug(f"{self.__class__.__name__}: PortMaster Post Install")
        self.gamelist_add_portmaster()

    def gamelist_add_portmaster(self):
        """
        Adds (or updates) PortMaster's own entry in the frontend's gamelist, from
        PortMaster/gameinfo.xml, on platforms whose ports list holds the launcher.
        """
        if not self.PORTMASTER_GAMELIST or not self.hm.cfg_data.get('gamelist_update', True):
            return

        pm_dir = self.hm.tools_dir / "PortMaster"
        gameinfo_file = pm_dir / "gameinfo.xml"

        try:
            gameinfo_tree = ET.parse(str(gameinfo_file))

        except (OSError, ET.ParseError) as err:
            logger.warning(f"Unable to add PortMaster to the gamelist, {gameinfo_file}: {err}")
            return

        ## Its paths are relative to where PortMaster is, which isn't the ports dir everywhere.
        for game in gameinfo_tree.getroot().findall('game'):
            for child in game:
                if child.tag in self.XML_PATH_FIX and child.text and child.text.strip().startswith('./'):
                    child.text = str(self.hm.tools_dir / child.text.strip()[2:])

        temp_dir = None if self.hm.temp_dir is None else str(self.hm.temp_dir)
        with tempfile.TemporaryDirectory(dir=temp_dir) as work_dir:
            temp_gameinfo = Path(work_dir) / "gameinfo.xml"
            gameinfo_tree.write(str(temp_gameinfo), encoding='unicode')
            self.gamelist_add(temp_gameinfo)

    def set_gcd_mode(self, mode=None):
        logger.info(f"{self.__class__.__name__}: Set GCD Mode {mode}")

    def get_gcd_modes(self):
        return tuple()

    def get_gcd_mode(self):
        logger.debug(f"{self.__class__.__name__}: Get GCD Mode")
        return None


class PlatformGCD_PortMaster:
    """
    gamecontrollerdb standard / xbox mode
    """

    def loaded(self):
        if self.get_gcd_mode() == 'xbox':
            self.WANT_XBOX_FIX = True

    def set_gcd_mode(self, gcd_mode=None):
        gamecontroller_file = self.hm.tools_dir / "PortMaster" / "gamecontrollerdb.txt"
        mode_files = {
            'standard': self.hm.tools_dir / "PortMaster" / ".Backup" / "donottouch.txt",
            'xbox': self.hm.tools_dir / "PortMaster" / ".Backup" / "donottouch_x.txt",
            }

        logger.info(f"{self.__class__.__name__}: Set GCD Mode: {gcd_mode}")

        if gcd_mode:
            if gcd_mode not in mode_files:
                logger.debug(f"Unknown gcd_mode {gcd_mode}")
                return

            if not mode_files[gcd_mode].is_file():
                logger.debug(f"Unknown gcd_mode {gcd_mode} file.")
                return

            shutil.copy(mode_files[gcd_mode], gamecontroller_file)

            self.hm.cfg_data['gcd-mode'] = gcd_mode
            self.hm.save_config()

        else:
            logger.debug(f"Weird {gcd_mode}")

    def get_gcd_modes(self):
        return ('standard', 'xbox')

    def get_gcd_mode(self):
        gamecontroller_file = self.hm.tools_dir / "PortMaster" / "gamecontrollerdb.txt"

        gcd_mode = self.hm.cfg_data.get('gcd-mode', None)

        if gcd_mode not in self.get_gcd_modes():
            gcd_mode = None

        if gcd_mode is None:
            if gamecontroller_file.is_file():
                if "# Xbox 360 Layout" in gamecontroller_file.read_text():
                    gcd_mode = 'xbox'

            if gcd_mode is None:
                gcd_mode = 'standard'

            self.hm.cfg_data['gcd-mode'] = gcd_mode
            self.hm.save_config()

        logger.debug(f"{self.__class__.__name__}: Get GCD Mode: {gcd_mode}")
        return gcd_mode


class PlatformTesting(PlatformBase):
    WANT_XBOX_FIX = False
    WANT_SWAP_BUTTONS = False

    def gamelist_file(self):
        return self.hm.scripts_dir / 'gamelist.xml'
