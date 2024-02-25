#!/usr/bin/env python3

import datetime
import os
import sys


def load_info(main_file):
    ST_HEAD, ST_INFO, ST_END = 0, 1, 2
    output_data = {
        "version_text": "",
        "version": None,
        "version_line": None,
        "release": None,
        "release_line": None,
        "all_data": [],
        }

    state = ST_HEAD
    lineno = -1
    with open(main_file, "r") as fh:
        for line in fh:
            lineno += 1
            line = line.rstrip("\n")
            output_data["all_data"].append(line)

            if line == "":
                continue

            if state == ST_HEAD:
                if line.strip().startswith("## -- BEGIN"):
                    state = ST_INFO
                continue

            if state == ST_INFO:
                if line.startswith("HARBOURMASTER_VERSION"):
                    output_data["version_text"] = "HARBOURMASTER_VERSION"
                    output_data["version"] = line.split("'")[-2]
                    output_data["version_line"] = lineno

                if line.startswith("PORTMASTER_RELEASE_CHANNEL"):
                    output_data["release"] = line.split("'")[-2]
                    output_data["release_line"] = lineno

                if line.startswith("PORTMASTER_VERSION"):
                    output_data["version_text"] = "PORTMASTER_VERSION"
                    output_data["version"] = line.split("'")[-2]
                    output_data["version_line"] = lineno

                if line.strip().startswith("## -- END"):
                    state = ST_END

                continue

    return output_data


def dump_info(main_file, info_data):
    with open(main_file, "w") as fh:
        fh.write("\n".join(info_data["all_data"]))
        fh.write("\n")


def main(argv):
    if len(argv) == 1:
        release_type = "alpha"
        version_number = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d-%H%M")

    elif len(argv) == 2:
        release_type = argv[1]
        version_number = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d-%H%M")

    else:
        release_type = argv[1]
        version_number = argv[2]

    pugwash_data = load_info("PortMaster/pugwash")

    print(f"{pugwash_data["version"]} now {version_number}")

    pugwash_data["all_data"][pugwash_data["version_line"]] = \
        f"{pugwash_data["version_text"]} = '{version_number}'"

    if pugwash_data["release"]:
        pugwash_data["all_data"][pugwash_data["release_line"]] = \
            f"PORTMASTER_RELEASE_CHANNEL = '{release_type}'"

    dump_info("PortMaster/pugwash", pugwash_data)


if __name__ == '__main__':
    main(sys.argv)
