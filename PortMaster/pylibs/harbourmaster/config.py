
# System imports
import pathlib
import platform
import os
import textwrap

from pathlib import Path

# Included imports

from loguru import logger


################################################################################
## Override this for custom tools/ports directories

HM_TOOLS_DIR=None
HM_PORTS_DIR=None
HM_UPDATE_FREQUENCY=(60 * 60 * 1)  # Only check automatically once per hour.

HM_TESTING=False
HM_PERFTEST=False

################################################################################
## The following code is a simplification of the PortMaster toolsloc and whichsd code.
HM_DEFAULT_PORTS_DIR = Path("/roms/ports")
HM_DEFAULT_TOOLS_DIR = Path("/roms/ports")

if (Path().cwd() / '.git').is_dir():
    ## For testing
    HM_DEFAULT_TOOLS_DIR = Path('.').absolute()
    HM_DEFAULT_PORTS_DIR = Path('ports/').absolute()
    HM_TESTING=True
elif Path("/opt/tools/PortMaster/").is_dir():
    HM_DEFAULT_TOOLS_DIR = Path("/opt/tools")
elif Path("/opt/system/Tools/PortMaster/").is_dir():
    HM_DEFAULT_TOOLS_DIR = Path("/opt/system/Tools")
elif Path("/storage/roms/ports").is_dir():
    HM_DEFAULT_TOOLS_DIR = Path("/storage/roms/ports")
    HM_DEFAULT_PORTS_DIR = Path("/storage/roms/ports")
else:
    HM_DEFAULT_TOOLS_DIR = Path("/roms/ports")

if Path("/roms2/ports").is_dir():
    HM_DEFAULT_PORTS_DIR = Path("/roms2/ports")

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


if 'HM_PERFTEST' in os.environ:
    HM_PERFTEST=True


HM_SOURCE_DEFAULTS = {
    "020_portmaster.source.json": textwrap.dedent("""
    {
        "prefix": "pm",
        "api": "PortMasterV1",
        "name": "PortMaster",
        "url": "https://api.github.com/repos/PortsMaster/PortMaster-Releases/releases/latest",
        "last_checked": null,
        "version": 1,
        "data": {}
    }
    """),
    "021_runtimes.source.json": textwrap.dedent("""
    {
        "prefix": "pr",
        "api": "GitHubRawReleaseV1",
        "name": "PortMaster Runtime",
        "url": "https://api.github.com/repos/PortsMaster/PortMaster-Runtime/releases/latest",
        "last_checked": null,
        "version": 1,
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


__all__ = (
    'HM_UPDATE_FREQUENCY',
    'HM_TOOLS_DIR',
    'HM_PORTS_DIR',
    'HM_DEFAULT_TOOLS_DIR',
    'HM_DEFAULT_PORTS_DIR',
    'HM_GENRES',
    'HM_SOURCE_DEFAULTS',
    'HM_TESTING',
    'HM_PERFTEST',
    )
