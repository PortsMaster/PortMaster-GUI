#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# Which hardware a Test Suite report came from, whatever the CFW calls it: muOS says
# tui-brick-pro, knulli trimui-brick-pro, spruce "TrimUI Brick Pro" (or just its SoC,
# sun50iw10). The coverage grid in matrix.py has one row per device.
#
#   python3 -I tools/test_suite/devices.py --refresh    # update data/device_info.json
#
# data/device_info.json is PortMaster-Info's device list (what device-a-roo shows): the
# devices and CFWs PortMaster supports, for the grid's untested-but-supported cells.
# Standard library only, Python 3.7.

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path


DEVICE_INFO_PATH = Path(__file__).resolve().parent / "data" / "device_info.json"
DEVICE_INFO_URL = "https://raw.githubusercontent.com/PortsMaster/PortMaster-Info/refs/heads/main/device_info.json"

## device_info.json's CFW names (any case) as reports spell them.
CFW_NAMES = {
    "amberelec": "AmberELEC",
    "arkos": "ArkOS",
    "arkos (wummle)": "ArkOS wuMMLe",
    "batocera": "Batocera",
    "emuelec": "EmuELEC",
    "knulli": "knulli",
    "muos": "muOS",
    "retrodeck": "RetroDECK",
    "rocknix": "ROCKNIX",
    "thera": "TheRA",
    "trimui": "TrimUI",
    }

## Words a name may start with that aren't part of the model: "Anbernic RG CubeXX" is rg-cubexx.
MAKER_WORDS = ("anbernic", "trimui", "tui", "miyoo", "powkiddy", "retroid", "magicx", "mgx", "mangmi",
               "gameconsole", "udt", "batlexp", "hardkernel", "gameforce", "gamekiddy", "valve")

## The devices reports have come from, and PortMaster-Info's models they cover. Each:
##   name, maker, aliases (any spelling: matched after
##   normalising), PortMaster-Info models it stands for, SoC rules ((soc, display), for spruce
##   builds that only reported the SoC).
DEVICES = (
    ("Anbernic RG CubeXX", "Anbernic", ("rgcubexx", "rgcubexxh", "AnbernicRGCubeXX"), ("Anbernic RGCUBEXX",), ()),
    ("Anbernic RG35XX SP", "Anbernic", ("rg35xxsp", "AnbernicXX640480NoStick"), ("Anbernic RG35XX SP",), ()),
    ("Anbernic RG35XX 2024", "Anbernic", ("rg35xx2024",), (), ()),
    ("Anbernic RG35XX Pro", "Anbernic", ("rg35xxpro",), (), ()),
    ("Anbernic RG34XX", "Anbernic", ("rg34xxh", "rg34xx"), ("Anbernic RG34XX",), ()),
    ("Anbernic RG28XX", "Anbernic", ("rg28xx", "rg28xxh"), ("Anbernic RG28XX",), ()),
    ("Anbernic RG353M", "Anbernic", ("rg353m",), ("Anbernic RG353 M/V/P",), ()),
    ("Anbernic RG353V", "Anbernic", ("rg353v",), ("Anbernic RG353 M/V/P",), ()),
    ("Anbernic RG353P", "Anbernic", ("rg353p",), ("Anbernic RG353 M/V/P",), ()),
    ("Anbernic RG353VS", "Anbernic", ("rg353vs",), ("Anbernic RG353 VS/PS",), ()),
    ("Anbernic RG353PS", "Anbernic", ("rg353ps",), ("Anbernic RG353 VS/PS",), ()),
    ("Anbernic RG351P/M", "Anbernic", ("rg351p", "rg351m"), ("Anbernic RG351P/M",), ()),
    ("Anbernic RG Vita Pro", "Anbernic", ("rgvitapro",), (), ()),
    ("Batlexp G350", "Batlexp", ("g350", "rkg350v", "rkg350"), (), ()),
    ("MagicX Zero 28", "MagicX", ("zero28", "mgxzero28", "magicxzero28"), (), (("sun50iw10", "640x480"),)),
    ("MANGMI Air X", "MANGMI", ("airxmq66", "mq66", "airx"), (), ()),
    ("Miniloong Pocket 1", "Miniloong", ("miniloong", "miniloongpocket1", "mlp1"), (), ()),
    ("Miyoo Flip", "Miyoo", ("miyooflip", "flip", "miyoork3566355v10board"), (), ()),
    ("Powkiddy RGB30", "Powkiddy", ("rgb30", "powkiddyrgb30akawonderfullyweirdunit"), ("Powkiddy RGB30",), ()),
    ("Retroid Pocket 5", "Retroid", ("rp5", "retroidpocket5", "pocket5"), ("Retroid Pocket 5",), ()),
    ("Retroid Pocket Mini", "Retroid", ("rpmini", "retroidpocketmini", "pocketmini"), ("Retroid Pocket Mini",), ()),
    ("Retroid Pocket Nova", "Retroid", ("rpnova", "retroidpocketnova", "pocketnova"), (), ()),
    ("R36 Ultra X", "Game Console", ("r36ultrax",), (), ()),
    ("Steam Deck", "Valve", ("steamdeck", "steamdeckoled", "jupiter", "galileo"), ("SteamDeck",), ()),
    ("TrimUI Brick", "TrimUI", ("trimuibrick", "tuibrick", "brick"), ("TrimUI Brick",), (("sun50iw10", "1024x768"),)),
    ("TrimUI Brick Pro", "TrimUI", ("trimuibrickpro", "tuibrickpro", "brickpro"), (), ()),
    ("TrimUI Smart Pro", "TrimUI", ("trimuismartpro", "tuispoon", "smartpro"), ("TrimUI Smart Pro",), (("sun50iw10", "1280x720"),)),
    ("TrimUI Smart Pro S", "TrimUI", ("trimuismartpros", "smartpros"), (), (("sun55iw3", ""),)),
    ("R33S", "Game Console", ("r33s",), ("R33S Retro Handheld",), ()),
    ("R35S", "Game Console", ("r35s",), ("R35S Retro Handheld",), ()),
    ("R36S", "Game Console", ("r36s",), ("R36S Retro Handheld",), ()),
    ("MagicX XU10", "MagicX", ("xu10",), ("XU10 Retro Handheld",), ()),
    ("A10 Mini", "Other", ("a10mini",), (), ()),
    )

OTHER = "Other"

## Devices close enough that a report on one says a lot about the others (same SoC, same
## builds of each CFW): the grid groups them, and tints a member's empty cells when another
## member has reports there.
FAMILIES = (
    ("Anbernic RGxxXX (H700)", ("Anbernic RG CubeXX", "Anbernic RG28XX", "Anbernic RG34XX", "Anbernic RG34XX SP",
                                "Anbernic RG35XX 2024", "Anbernic RG35XX H", "Anbernic RG35XX PLUS", "Anbernic RG35XX Pro",
                                "Anbernic RG35XX SP", "Anbernic RG40XX H", "Anbernic RG40XX V")),
    ("Anbernic RG353 / ARC (RK3566)", ("Anbernic RG353M", "Anbernic RG353V", "Anbernic RG353P", "Anbernic RG353VS",
                                       "Anbernic RG353PS", "Anbernic RG ARC-D", "Anbernic RG ARC-S", "Anbernic RG503")),
    ("Anbernic RG351 (RK3326)", ("Anbernic RG351MP", "Anbernic RG351P/M", "Anbernic RG351V")),
    ("R3x clones (RK3326)", ("R33S", "R35S", "R36S", "R36 Ultra X")),
    ("ODROID Go (RK3326)", ("Hardkernel ODROID GO Advance", "Hardkernel ODROID GO Super")),
    ("Powkiddy RK3566", ("Powkiddy RGB30", "Powkiddy RK2023", "Powkiddy X55", "Powkiddy RGB10MAX3")),
    ("Powkiddy RK3326", ("Powkiddy RGB10", "Powkiddy RGB20S")),
    ("Retroid Pocket 5 / Mini (SD865)", ("Retroid Pocket 5", "Retroid Pocket Mini")),
    ("TrimUI Brick / Smart Pro (A133P)", ("TrimUI Brick", "TrimUI Brick Pro", "TrimUI Smart Pro")),
    )


def normalise(name):
    """ "Anbernic RG CubeXX" -> "rgcubexx": lowercase letters and digits, without a maker word."""
    text = re.sub(r"[^a-z0-9]", "", str(name).lower())
    for word in MAKER_WORDS:
        if text.startswith(word) and len(text) > len(word):
            return text[len(word):]

    return text


class Device:
    def __init__(self, name, maker, aliases=(), models=(), rules=(), family=""):
        self.name = name
        self.maker = maker
        self.family = family
        self.aliases = {normalise(alias) for alias in aliases + (name,)}
        self.models = tuple(models)
        self.rules = tuple(rules)
        ## {CFW as reports spell it: its device id}, from PortMaster-Info.
        self.supported = {}

    @property
    def short_name(self):
        """The name without its maker, as the grid lists it under the maker."""
        if self.name.lower().startswith(self.maker.lower() + " "):
            return self.name[len(self.maker) + 1:]
        return self.name

    def __repr__(self):
        return f"Device({self.name!r})"


def load_device_info(path=DEVICE_INFO_PATH):
    """PortMaster-Info's {model: {CFW: info}}, {} if it can't be read."""
    try:
        data = json.loads(Path(path).read_text())

    except (OSError, ValueError):
        return {}

    return data if isinstance(data, dict) else {}


def build_catalogue(device_info=None):
    """[Device]: DEVICES, then PortMaster-Info's models none of them stand for."""
    device_info = load_device_info() if device_info is None else device_info
    devices = [Device(*entry) for entry in DEVICES]
    covered = {model for device in devices for model in device.models}

    for model, cfws in sorted(device_info.items()):
        if not isinstance(cfws, dict):
            continue

        infos = [info for info in cfws.values() if isinstance(info, dict)]
        ids = {str(info.get('device', "")) for info in infos} - {""}
        if model in covered:
            targets = [device for device in devices if model in device.models]
        else:
            ## A model under another spelling (its name or device id is an alias) joins that one.
            keys = {normalise(model)} | {normalise(device_id) for device_id in ids}
            targets = [device for device in devices if device.aliases & keys][:1]
            if not targets:
                maker = next((str(info['manufacturer']) for info in infos if info.get('manufacturer')), OTHER)
                targets = [Device(model, maker)]
                devices.append(targets[0])

        for device in targets:
            for cfw, info in cfws.items():
                if not isinstance(info, dict):
                    continue
                name = CFW_NAMES.get(cfw.lower(), cfw)
                device.supported[name] = str(info.get('device', ""))
            ## Only a model that is just this device lends it its ids ("rg353m" isn't the RG353V).
            if len(targets) == 1:
                device.aliases |= {normalise(device_id) for device_id in ids}

    families = {name: family for family, names in FAMILIES for name in names}
    for device in devices:
        device.family = families.get(device.name, "")

    return devices


_CATALOGUE = None


def catalogue():
    global _CATALOGUE
    if _CATALOGUE is None:
        _CATALOGUE = build_catalogue()
    return _CATALOGUE


def identify(row, devices=None):
    """The Device a report row came from: by its device name, then spruce's platform name, then
    its SoC and display. None if nothing matches."""
    devices = catalogue() if devices is None else devices
    for field in ('device', 'platform', 'model'):
        key = normalise(row.get(field) or "")
        if not key:
            continue
        for device in devices:
            if key in device.aliases:
                return device

    soc = normalise(row.get('device') or "")
    for device in devices:
        for rule_soc, display in device.rules:
            if soc == rule_soc and display in ("", row.get('display')):
                return device

    return None


def refresh(path=DEVICE_INFO_PATH, url=DEVICE_INFO_URL):
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not isinstance(data, dict) or not data:
        raise ValueError("not a device list")

    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="The Test Suite's device catalogue")
    parser.add_argument("--refresh", action="store_true", help=f"download {DEVICE_INFO_URL}")
    options = parser.parse_args(argv)

    if options.refresh:
        print(f"{len(refresh())} models -> {DEVICE_INFO_PATH}")

    for device in catalogue():
        print(f"{device.maker:14} {device.name:28} {', '.join(sorted(device.supported)) or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
