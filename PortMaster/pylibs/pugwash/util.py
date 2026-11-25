# SPDX-License-Identifier: MIT
#
# Small helpers for the GUI.

import subprocess
from itertools import chain
from pathlib import Path
import harbourmaster


################################################################################
## Code starts here.
def is_process_running(process_name):
    """
    Check if a process with the given name is running using pgrep.
    """

    try:
        output = subprocess.check_output(['pgrep', '-f', process_name], stderr=subprocess.DEVNULL)
        return bool(output.strip())  # If output exists, the process is running
    except subprocess.CalledProcessError:
        return False  # pgrep returns non-zero exit code if no process matches


## Where to find the battery level (0-100), first one that reads wins.
BATTERY_PATHS = (
    Path("/run/muos/battery/capacity"),  # muOS (newer releases), calibrated
    Path("/tmp/battery.percent"),
    Path("/sys/class/power_supply/battery/capacity"),
    Path("/sys/class/power_supply/axp2202-battery/capacity"),
    Path("/sys/class/power_supply/BAT1/capacity"),
    Path("/sys/class/power_supply/qcom-battery/capacity"),
    )

POWER_SUPPLY_DIR = Path("/sys/class/power_supply")


## The file battery_level() last read, for each search: it keeps reading that one.
_BATTERY_FILES = {}


def _system_battery_paths(power_supply_dir):
    """The capacity files of the system's batteries (not a controller's, scope Device)."""
    for type_file in sorted(power_supply_dir.glob("*/type")):
        scope_file = type_file.parent / "scope"
        try:
            if type_file.read_text().strip() == "Battery" and (
                    not scope_file.exists() or scope_file.read_text().strip() == "System"):
                yield type_file.parent / "capacity"

        except OSError:
            pass


def _read_level(battery_file):
    try:
        return int(Path(battery_file).read_text().strip())

    except (OSError, ValueError):
        return None


def battery_level(paths=BATTERY_PATHS, power_supply_dir=POWER_SUPPLY_DIR):
    """
    The battery level as an int, or None if there is no battery we can read.
    Files that can't be read or don't hold a number are skipped.

    The file that read last time is read first; only if it fails are the paths checked again.
    """
    key = (tuple(paths), power_supply_dir)
    cached = _BATTERY_FILES.pop(key, None)
    if cached is not None:
        level = _read_level(cached)
        if level is not None:
            _BATTERY_FILES[key] = cached
            return level

    for battery_file in chain(paths, _system_battery_paths(power_supply_dir)):
        level = _read_level(battery_file)
        if level is not None:
            _BATTERY_FILES[key] = battery_file
            return level

    return None


__IP_ADDRESS=None
def get_ip_address(force_update=False):
    global __IP_ADDRESS

    if not force_update and __IP_ADDRESS is not None:
        return __IP_ADDRESS

    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('1.1.1.1', 1))
        __IP_ADDRESS = s.getsockname()[0]

    except Exception:
        __IP_ADDRESS = None

    finally:
        s.close()

    return __IP_ADDRESS


def format_progress(amount, total, fmt=None):
    if fmt == 'data':
        if total is None:
            return f"{harbourmaster.nice_size(amount)}"

        else:
            return f"{harbourmaster.nice_size(amount)} / {harbourmaster.nice_size(total)}"

    elif fmt == '%':
        if total is None:
            return f"{min(amount, 100):.0f} %"

        else:
            return f"{min(amount / total * 100, 100):.0f} %"

    else:
        if total is None:
            return f"{amount}"

        else:
            return f"{amount} / {total}"
