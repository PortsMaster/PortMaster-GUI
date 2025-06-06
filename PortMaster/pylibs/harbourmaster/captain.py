
# SPDX-License-Identifier: MIT

# System imports
import fnmatch
import json
import pathlib
import shutil
import subprocess
import zipfile

from pathlib import Path

# Included imports
import utility

from loguru import logger
from utility import cprint

# Module imports
from .config import *
from .util import *
from .info import *


class BadPort(HarbourException):
    ...


def check_port(port_name, zip_file, extra_info=None):
    items = []
    scripts = []
    dirs = []

    port_info_file = None
    game_info_file = None

    port_info_file_fix = False
    game_info_file_fix = False

    with zipfile.ZipFile(zip_file, 'r') as zf:
        for file_info in zf.infolist():
            if file_info.filename.startswith('/'):
                ## Sneaky
                logger.error(f"Port {port_name} has an illegal file {file_info.filename!r}, aborting.")
                raise BadPort()

            if file_info.filename.startswith('../'):
                ## Little
                logger.error(f"Port {port_name} has an illegal file {file_info.filename!r}, aborting installation.")
                raise BadPort()

            if '/../' in file_info.filename:
                ## Shits
                logger.error(f"Port {port_name} has an illegal file {file_info.filename!r}, aborting.")
                raise BadPort()

            if '/' in file_info.filename:
                parts = file_info.filename.split('/')

                if parts[0] not in dirs:
                    items.append(parts[0] + '/')
                    dirs.append(parts[0])

                if len(parts) == 2:
                    if parts[1].lower().endswith('.port.json') or parts[1] == 'port.json':
                        ## TODO: add the ability for multiple port folders to have multiple port.json files. ?
                        if port_info_file is not None:
                            logger.warning(f"Port {port_name} has multiple port.json files.")
                            logger.warning(f"- Before: {port_info_file!r}")
                            logger.warning(f"- Now:    {file_info.filename!r}")

                        port_info_file = file_info.filename
                        port_info_file_fix = False

                    if parts[1] == 'gameinfo.xml':
                        game_info_file = file_info.filename
                        game_info_file_fix = False

                if file_info.filename.lower().endswith('.sh'):
                    logger.warning(f"Port {port_name} has {file_info.filename} inside, this can cause issues.")

            else:
                if file_info.filename.lower().endswith('.sh'):
                    scripts.append(file_info.filename)
                    items.append(file_info.filename)

                elif file_info.filename.lower() in HM_ACCEPTABLE_NON_BASH_TOP_LEVEL_FILES:
                    # https://tenor.com/view/community-ken-jeong-ben-chang-ill-allow-it-allowed-gif-4468552
                    if file_info.filename.lower() == 'port.json':
                        if port_info_file is not None:
                            logger.warning(f"Port {port_name} has multiple port.json files.")
                            logger.warning(f"- Before: {port_info_file!r}")
                            logger.warning(f"- Now:    {file_info.filename!r}")

                        port_info_file = file_info.filename
                        port_info_file_fix = True

                    elif file_info.filename.lower() == 'gameinfo.xml':
                        game_info_file = file_info.filename
                        game_info_file_fix = True

                else:
                    logger.warning(f"Port {port_name} contains {file_info.filename} at the top level, but it is not a shell script.")

        if len(dirs) == 0:
            logger.error(f"Port {port_name} has no directories, aborting.")
            raise BadPort()

        if len(scripts) == 0:
            logger.error(f"Port {port_name} has no scripts, aborting.")
            raise BadPort()

        if port_info_file is not None:
            port_info_data = json_safe_loads(zf.read(port_info_file).decode('utf-8'))

            if not isinstance(port_info_data, dict):
                logger.error(f"Unable to load port.json file from {port_info_file}")
                raise BadPort()

            port_info = port_info_load(port_info_data)

        else:
            port_info_data = None
            port_info_file = f"{dirs[0]}/port.json"

            logger.warning(f"No port info file found, recommended name is {port_info_file}")
            port_info = port_info_load({})

    ## These two are always overriden.
    port_info['name'] = name_cleaner(port_name)
    port_info['items'] = items

    # if port_info_data != port_info:
    #     logger.warning(f"port.json is different from what is expected:\n{json.dumps(port_info, indent=4)}")

    if extra_info is not None:
        if port_info_file_fix:
            port_info_file = f"{dirs[0]}/{port_info_file}"

        if game_info_file_fix:
            game_info_file = f"{dirs[0]}/{game_info_file}"

        extra_info['port_info_file'] = port_info_file
        extra_info['gameinfo_xml'] = game_info_file
        extra_info['port_dir'] = dirs[0]

    return port_info


__all__ = (
    'check_port',
    )

