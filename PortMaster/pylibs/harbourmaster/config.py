
# SPDX-License-Identifier: MIT


# System imports
import collections
import json
import os
import pathlib
import platform
import re
import subprocess
import textwrap

from pathlib import Path

# Included imports

from loguru import logger


################################################################################
## Override this for custom tools/ports directories

HM_TOOLS_DIR=None
HM_PORTS_DIR=None
HM_SCRIPTS_DIR=None
HM_UPDATE_FREQUENCY=(60 * 60 * 1)  # Only check automatically once per hour.

HM_TESTING=False
HM_PERFTEST=False

## Extra debugging output, the scripts set this.
HM_DEBUG=False

## Maximum temporary size is 100 mb, this can cause errors on TrimUI and muOS.
HM_MAX_TEMP_SIZE = 1024 * 1024 * 100

################################################################################
## The following code is a simplification of the PortMaster toolsloc and whichsd code.
HMPaths = collections.namedtuple('HMPaths', ['tools_dir', 'ports_dir', 'scripts_dir', 'testing'])


def detect_paths(root="/", cwd=None, environ=None, home=None, df_output=None):
    """
    Work out the default tools/ports/scripts directories for this device.

    Every absolute path is looked up under `root`, and `cwd`, `environ`, `home`
    and `df_output` can be given, so this can be tested against a fake filesystem.
    `df_output` is a callable returning the output of `df`.
    """
    root = Path(root)
    cwd = Path.cwd() if cwd is None else Path(cwd)
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)

    if df_output is None:
        def df_output():
            return subprocess.getoutput(['df'])

    def _p(path):
        return root / str(path).lstrip('/')

    tools_dir   = Path("/roms/ports")
    ports_dir   = Path("/roms/ports")
    scripts_dir = Path("/roms/ports")
    testing = False

    if (cwd / '.git').is_dir():
        ## For testing
        tools_dir   = cwd.absolute()
        ports_dir   = (cwd / 'ports').absolute()
        scripts_dir = (cwd / 'ports').absolute()
        testing = True

    elif _p("/mnt/SDCARD/spruce").is_dir():
        ## spruceOS (Miyoo Flip, TrimUI, Anbernic, Powkiddy RGB30...)
        tools_dir   = Path("/mnt/SDCARD/Persistent/portmaster")
        ports_dir   = Path("/mnt/SDCARD/Roms/ports")
        scripts_dir = Path("/mnt/SDCARD/Roms/ports")

    elif _p("/mnt/SDCARD/MIYOO_EX/PortMaster").is_dir():
        ## TrimUI Smart Pro
        tools_dir   = Path("/mnt/SDCARD/MIYOO_EX/PortMaster")
        ports_dir   = Path("/mnt/SDCARD/MIYOO_EX/ports")
        scripts_dir = Path("/mnt/SDCARD/MIYOO_EX/ports")

    elif _p("/mnt/SDCARD/Apps/PortMaster").is_dir():
        ## TrimUI Smart Pro
        tools_dir   = Path("/mnt/SDCARD/Apps/PortMaster")
        ports_dir   = Path("/mnt/SDCARD/Data/ports")
        scripts_dir = Path("/mnt/SDCARD/Data/ports")

    elif _p("/userdata/roms/ports").is_dir():
        ## Batocera
        tools_dir   = Path(environ['XDG_DATA_HOME'])
        ports_dir   = Path("/userdata/roms/ports")
        scripts_dir = Path("/userdata/roms/ports")

    elif _p("/opt/muos").is_dir():
        ## muOS
        tools_dir   = Path("/mnt/mmc/MUOS")
        ports_dir   = Path("/mnt/mmc/ports")
        scripts_dir = Path("/mnt/mmc/ROMS/Ports")

        muos_mmc_toggle = _p('/mnt/mmc/MUOS/PortMaster/config/muos_mmc_master_race.txt')

        if not muos_mmc_toggle.is_file() and '/mnt/sdcard' in df_output():
            ports_dir   = Path("/mnt/sdcard/ports")
            scripts_dir = Path("/mnt/sdcard/ROMS/Ports")

    elif _p("/opt/system/Tools").is_dir():
        if _p("/roms2/tools").is_dir():
            tools_dir   = Path("/roms2/tools")
            ports_dir   = Path("/roms2/ports")
            scripts_dir = Path("/roms2/ports")

        else:
            tools_dir   = Path("/roms/tools")
            ports_dir   = Path("/roms/ports")
            scripts_dir = Path("/roms/ports")

    elif _p("/opt/tools/PortMaster").is_dir():
        tools_dir   = Path("/opt/tools")
        ports_dir   = Path("/roms/ports")
        scripts_dir = Path("/roms/ports")

    elif _p("/storage/roms/ports_scripts").is_dir():
        tools_dir   = Path("/storage/roms/ports")
        ports_dir   = Path("/storage/roms/ports")
        scripts_dir = Path("/storage/roms/ports_scripts")

    elif _p("/storage/roms/ports").is_dir():
        tools_dir   = Path("/storage/roms/ports")
        ports_dir   = Path("/storage/roms/ports")
        scripts_dir = Path("/storage/roms/ports")

    ## Check if retrodeck.cfg or retrodeck.json exists. Chose this file/location as platform independent from were retrodeck is installed.
    elif _p("/var/config/retrodeck/retrodeck.json").is_file() or (home / ".var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.json").is_file():
        rdconfig_file = _p("/var/config/retrodeck/retrodeck.json")
        tools_dir = Path("/var/data")

        if not rdconfig_file.is_file():
            rdconfig_file = (home / ".var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.json")
            tools_dir  = (home / ".var/app/net.retrodeck.retrodeck/data")

        rdhome = None
        ports_folder = None
        roms_folder  = None
        rdconfig_data = None

        with open(rdconfig_file, 'r') as fh:
            try:
                rdconfig_data = json.load(fh)
            except json.JSONDecodeError as err:
                logger.error(f"Unable to load {rdconfig_file}:{err.pos}:{err.lineno}:{err.colno}: {err.doc}")
                exit(255)

        if not isinstance(rdconfig_data, dict):
            logger.error(f"Unable to load the retrodeck.json: {rdconfig_file}.")
            exit(255)

        if 'rd_home_path' not in rdconfig_data.get('paths', {}):
            logger.error(f"Unable to find the rd_home_path value in {rdconfig_file}.")
            exit(255)

        rdhome = Path(rdconfig_data['paths']['rd_home_path'])

        roms_folder  = Path(rdconfig_data['paths'].get('roms_path',  rdhome / "roms"))
        ## Newer RetroDECK calls it portmaster_path.
        ports_folder = Path(
            rdconfig_data['paths'].get('ports_path') or
            rdconfig_data['paths'].get('portmaster_path') or
            rdhome / "PortMaster")

        ports_dir   = ports_folder / "ports"
        scripts_dir = roms_folder  / "portmaster"

    elif _p("/var/config/retrodeck/retrodeck.cfg").is_file() or (home / ".var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.cfg").is_file():
        rdconfig_file = _p("/var/config/retrodeck/retrodeck.cfg")
        tools_dir = Path("/var/data")

        if not rdconfig_file.is_file():
            rdconfig_file = (home / ".var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.cfg")
            tools_dir  = (home / ".var/app/net.retrodeck.retrodeck/data")

        rdhome = None
        ports_folder = None
        roms_folder = None

        with open(rdconfig_file, 'r') as fh:
            for line in fh:
                line = line.strip()

                if line.startswith('rdhome='):
                    rdhome = Path(line.split('=', 1)[-1])

                if line.startswith('ports_folder='):
                    ports_folder = Path(line.split('=', 1)[-1])

                if line.startswith('roms_folder='):
                    roms_folder = Path(line.split('=', 1)[-1])

        if rdhome is None:
            logger.error(f"Unable to find the rdhome variable in {rdconfig_file}.")
            exit(255)

        if roms_folder is None:
            roms_folder = rdhome / "roms"

        if ports_folder is None:
            ports_folder = rdhome / "PortMaster"

        ports_dir   = Path(ports_folder) / "ports"
        scripts_dir = Path(roms_folder)  / "portmaster"

    else:
        tools_dir = Path("/roms/ports")

    return HMPaths(tools_dir, ports_dir, scripts_dir, testing)


if 'XDG_DATA_HOME' not in os.environ:
    os.environ['XDG_DATA_HOME'] = str(Path().home() / '.local' / 'share')

if (Path().cwd() / '..' / '.git').is_dir():
    os.chdir(Path().cwd() / '..')

HM_DEFAULT_TOOLS_DIR, HM_DEFAULT_PORTS_DIR, HM_DEFAULT_SCRIPTS_DIR, HM_TESTING = detect_paths()

logger.debug(f"HM_DEFAULT_TOOLS_DIR:   {HM_DEFAULT_TOOLS_DIR}")
logger.debug(f"HM_DEFAULT_PORTS_DIR:   {HM_DEFAULT_PORTS_DIR}")
logger.debug(f"HM_DEFAULT_SCRIPTS_DIR: {HM_DEFAULT_SCRIPTS_DIR}")

## Default TOOLS_DIR
if HM_TOOLS_DIR is None:
    if 'HM_TOOLS_DIR' in os.environ:
        HM_TOOLS_DIR = Path(os.environ['HM_TOOLS_DIR'])
    else:
        HM_TOOLS_DIR = HM_DEFAULT_TOOLS_DIR
elif isinstance(HM_TOOLS_DIR, str):
    HM_TOOLS_DIR = Path(HM_TOOLS_DIR).resolve()
elif isinstance(HM_TOOLS_DIR, pathlib.PurePath):
    # This is good.
    pass
else:
    logger.error(f"{HM_TOOLS_DIR!r} is set to something weird.")
    exit(255)


## Default PORTS_DIR
if HM_PORTS_DIR is None:
    if 'HM_PORTS_DIR' in os.environ:
        HM_PORTS_DIR = Path(os.environ['HM_PORTS_DIR']).resolve()
    else:
        HM_PORTS_DIR = HM_DEFAULT_PORTS_DIR
elif isinstance(HM_PORTS_DIR, str):
    HM_PORTS_DIR = Path(HM_PORTS_DIR).resolve()
elif isinstance(HM_PORTS_DIR, pathlib.PurePath):
    # This is good.
    pass
else:
    logger.error(f"{HM_PORTS_DIR!r} is set to something weird.")
    exit(255)

## Default TOOLS_DIR
if HM_SCRIPTS_DIR is None:
    if 'HM_SCRIPTS_DIR' in os.environ:
        HM_SCRIPTS_DIR = Path(os.environ['HM_SCRIPTS_DIR'])
    else:
        HM_SCRIPTS_DIR = HM_DEFAULT_SCRIPTS_DIR
elif isinstance(HM_SCRIPTS_DIR, str):
    HM_SCRIPTS_DIR = Path(HM_SCRIPTS_DIR).resolve()
elif isinstance(HM_SCRIPTS_DIR, pathlib.PurePath):
    # This is good.
    pass
else:
    logger.error(f"{HM_SCRIPTS_DIR!r} is set to something weird.")
    exit(255)


if 'HM_PERFTEST' in os.environ:
    HM_PERFTEST=True


HM_SOURCE_DEFAULTS = {
    "020_portmaster.source.json": textwrap.dedent("""
    {
        "prefix": "pm",
        "api": "PortMasterV3",
        "name": "PortMaster",
        "url": "https://github.com/PortsMaster/PortMaster-New/releases/latest/download/ports.json",
        "last_checked": null,
        "version": 1,
        "data": {}
    }
    """),
    "021_portmaster.multiverse.source.json": textwrap.dedent("""
    {
        "prefix": "pmmv",
        "api": "PortMasterV3",
        "name": "PortMaster Multiverse",
        "url": "https://github.com/PortsMaster-MV/PortMaster-MV-New/releases/latest/download/ports.json",
        "last_checked": null,
        "version": 4,
        "data": {}
    }
    """),
    }


HM_GENRES = [
    "action",
    "adventure",
    "arcade",
    "casino/card",
    "fps",
    "platformer",
    "puzzle",
    "racing",
    "rhythm",
    "rpg",
    "simulation",
    "sports",
    "strategy",
    "visual novel",
    "other",
    ]


HM_SORT_ORDER = [
    "alphabetical",
    "recently_added",
    "recently_updated",
    "total_downloads",
    ]


HM_ACCEPTABLE_NON_BASH_TOP_LEVEL_FILES = [
    'cover.jpg',
    'cover.png',
    'gameinfo.xml',
    'port.json',
    'readme.md',
    'screenshot.jpg',
    'screenshot.png',
    ]


__all__ = (
    'HM_DEFAULT_PORTS_DIR',
    'HM_DEFAULT_TOOLS_DIR',
    'HM_DEFAULT_SCRIPTS_DIR',
    'HM_GENRES',
    'HM_PERFTEST',
    'HM_PORTS_DIR',
    'HM_SCRIPTS_DIR',
    'HM_SORT_ORDER',
    'HM_SOURCE_DEFAULTS',
    'HM_MAX_TEMP_SIZE',
    'HM_TESTING',
    'HM_TOOLS_DIR',
    'HM_UPDATE_FREQUENCY',
    'HM_ACCEPTABLE_NON_BASH_TOP_LEVEL_FILES',
    )
