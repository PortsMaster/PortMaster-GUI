#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import argparse
from pathlib import Path

ES_INPUT_CFG = "es_input.cfg"

GAMECONTROLLERDB_TXT = "gamecontrollerdb.txt"

TR_MAP = {
    "b" : "a",
    "a" : "b",
    "x" : "y",
    "y" : "x",
    "hotkeyenable" : "guide",
    "hotkey" : "guide",
    "up" : "dpup",
    "down" : "dpdown",
    "left" : "dpleft",
    "right" : "dpright",
    "leftshoulder" : "leftshoulder",
    "l2" : "leftshoulder",
    "leftthumb" : "leftstick",
    "l3" : "leftstick",
    "lefttrigger" : "lefttrigger",
    "rightshoulder" : "rightshoulder",
    "r2" : "rightshoulder",
    "rightthumb" : "rightstick",
    "r3" :  "rightstick",
    "righttrigger": "righttrigger",
    "select" : "back",
    "start" : "start",
    "leftanalogup" : "-lefty",
    "leftanalogleft" : "-leftx",
    "leftanalogdown" : "+lefty",
    "leftanalogright" : "+leftx",
    "rightanalogup" : "-righty",
    "rightanalogleft" : "-rightx",
    "rightanalogdown" : "+righty",
    "rightanalogright" : "+righty"
}

MAP_SUFFIX="platform:Linux,"

# -- Helper function --
# Pre Map
def premap_input(input_entry):
    input_name = input_entry["name"]
    input_type = input_entry["type"]
    input_id = input_entry["id"]
    input_value = input_entry["value"]


    invert_value = "-1"
    if input_value == "-1":
        invert_value = "1"

    if input_name == "joystick1left":
        leftanalogleft = map_input("leftanalogleft", input_type, input_id, input_value)
        leftanalogright = map_input("leftanalogright", input_type, input_id, invert_value)
        return f"{leftanalogleft}{leftanalogright}"
    elif input_name == "joystick1up":
        leftanalogup = map_input("leftanalogup", input_type, input_id, input_value)
        leftanalogdown = map_input("leftanalogdown", input_type, input_id, invert_value)
        return f"{leftanalogup}{leftanalogdown}"
    elif input_name == "joystick2left":
        rightanalogleft = map_input("rightanalogleft", input_type, input_id, input_value)
        rightanalogright = map_input("rightanalogright", input_type, input_id, invert_value)
        return f"{rightanalogleft}{rightanalogright}"
    elif input_name == "joystick2up":
        rightanalogup = map_input("rightanalogup", input_type, input_id, input_value)
        rightanalogdown = map_input("rightanalogdown", input_type, input_id, invert_value)
        return f"{rightanalogup}{rightanalogdown}"
    else:
         return f"{map_input(input_name, input_type, input_id, input_value)}"

# Map the actual button/hat/axis
def map_input(input_name, input_type, input_id, input_value):


    if not input_name in TR_MAP.keys():
      print(f"Invalid mapping {input_name}.")
      return ""

    tr_name = TR_MAP[input_name]

    print(f"{input_name} -> {tr_name}")

    if input_type == "axis":
        if int(input_value) < 0:
            return f"{tr_name}:-a{input_id},"
        else:
            # Most (save for a few misbehaved children...) triggers are [0, 1] instead of [-1, 1]
            # Shitty workaround for an emulationstation issue
            if "trigger" in input_name:
                return f"{tr_name}:a{input_id},"
            else:
                return f"{tr_name}:+a{input_id},"

    elif input_type == "button":
        return f"{tr_name}:b{input_id},"
    
    elif input_type == "hat":
        return f"{tr_name}:h{input_id}.{input_value},"
    
    else:
        print(f"Invalid entry {input_type}")
        return ""

def main():

    parser = argparse.ArgumentParser(description='ES input to gamecontrollerdb mapper')
    parser.add_argument('filepath', help='gamecontrollerdb file path (eg: /tmp/gamecontrollerdb.txt)')

    args = parser.parse_args()

    deviceGUID_list = []

    with open(args.filepath,"r") as gamecontrollerdb:
        for line in gamecontrollerdb.readlines():
            line = line.strip()
            if line.startswith("#") or len(line) == 0:
                continue
            deviceGUID = line.split(",")[0]
            deviceGUID_list.append(deviceGUID)

    es_input_path = Path.home() / "configs" / "emulationstation" / ES_INPUT_CFG

    if not es_input_path.is_file():
        es_input_path = Path.home() / ".config" / "emulationstation" / ES_INPUT_CFG

    with open(args.filepath, "w+") as gamecontrollerdb:

        gamecontrollerdb.write("\n# Custom Entries\n")

        print("## ES Dev Mapper ##")

        tree = ET.parse(es_input_path)
        root = tree.getroot()

        for entry_l1 in root:
            if entry_l1.tag == "inputConfig":
                inputConfig = entry_l1.attrib

                deviceGUID = inputConfig['deviceGUID']

                # Ignore keyboards
                if deviceGUID == "-1":
                    continue

                # Check if GUID exists in gamecontrollerdb.txt
                if deviceGUID in deviceGUID_list:
                    print("Already mapped...")
                    continue

                deviceName = inputConfig['deviceName']

                mapping = ""

                for entry_l2 in entry_l1:
                    if entry_l2.tag == "input":
                        mapping = f"{mapping}{premap_input(entry_l2.attrib)}"
                
                if len(mapping) > 0:
                    mapping = f"{deviceGUID},{deviceName},{mapping}{MAP_SUFFIX}"
                    gamecontrollerdb.write(f"{mapping}\n")
                    print(f"{mapping}\n\n")

                else:
                    print("Failed to map anything.")

if __name__ == '__main__':
    main()