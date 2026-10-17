# SPDX-License-Identifier: MIT
#
# The PortMaster GUI. PortMaster/pugwash bootstraps pylibs and runs it.

from pathlib import Path

## The pylibs directory, default_theme/, resources/ and locales/ live there.
PYLIB_PATH = Path(__file__).resolve().parent.parent

## Version info. The real values live in the PortMaster/pugwash script (tools/pm_release.py
## and do_release.sh edit them there), which calls set_version_info() before importing
## anything else from pugwash.
PORTMASTER_VERSION = 'unknown'
PORTMASTER_RELEASE_CHANNEL = 'developer'
PORTMASTER_MIN_VERSION = '0'
PORTMASTER_RELEASE_URL = 'https://github.com/PortsMaster/PortMaster-GUI/releases/latest/download/'
PORTMASTER_RELEASE_VALUES = ('stable', 'beta', 'alpha')
PORTMASTER_UPDATE_FREQUENCY = (60 * 60 * 1)
PORTMASTER_DEBUG = False


def set_version_info(**values):
    """
    Called by the PortMaster/pugwash script with its version block.
    """
    for name, value in values.items():
        if name not in globals() or not name.startswith('PORTMASTER_'):
            raise ValueError(f"unknown version info {name!r}")

        globals()[name] = value

    import harbourmaster.config
    harbourmaster.config.HM_DEBUG = globals()['PORTMASTER_DEBUG']
