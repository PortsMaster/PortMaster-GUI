#!/usr/bin/env python3

import os
import sys


def version_parse(version):
    result = []

    i = 0
    while i < len(version):
        number = ""
        suffix = ""
        while i < len(version):
            if not version[i].isnumeric():
                break

            number += version[i]
            i += 1

        if number != "":
            result.append(int(number))

        while i < len(version):
            if version[i].isnumeric():
                break

            c = version[i]
            i += 1

            if c not in '()[],_.-':
                suffix += c

        if suffix != "":
            result.append(suffix)

    return result


def version_str(version):
    return ".".join(map(str, version))


def load_info(main_file):
    ST_HEAD, ST_INFO, ST_END = 0, 1, 2
    output_data = {
        "version": None,
        "version_line": None,
        "channel": None,
        "channel_line": None,
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
                if line.strip() == "## -- BEGIN PORTMASTER INFO --":
                    state = ST_INFO
                continue

            if state == ST_INFO:
                if line.startswith("PORTMASTER_VERSION"):
                    output_data["version"] = version_parse(line.split("'")[-2])
                    output_data["version_line"] = lineno

                if line.startswith("PORTMASTER_RELEASE_CHANNEL"):
                    output_data["channel"] = line.split("'")[-2]
                    output_data["channel_line"] = lineno

                if line.strip() == "## -- END PORTMASTER INFO --":
                    state = ST_END

                continue

    return output_data


def main(argv):
    pugwash_data = load_info("PortMaster/pugwash")

    for command in argv[1:]:
        if command == 'stable':
            pugwash_data["channel"] = "stable"

        elif command == 'beta':
            pugwash_data["channel"] = "beta"

        elif command == "major":
            pugwash_data["version"][0] += 1
            pugwash_data["version"][1] = 0
            pugwash_data["version"][2] = 0

        elif command == "minor":
            pugwash_data["version"][1] += 1
            pugwash_data["version"][2] = 0

        elif command == "patch":
            pugwash_data["version"][2] += 1

        else:
            print(f"Unknown command: {command}")

    print(pugwash_data["version"])
    print(pugwash_data["channel"])

    pugwash_data["all_data"][pugwash_data["version_line"]] = \
        f"PORTMASTER_VERSION = '{version_str(pugwash_data['version'])}'"

    pugwash_data["all_data"][pugwash_data["channel_line"]] = \
        f"PORTMASTER_RELEASE_CHANNEL = '{pugwash_data['channel']}'"

    with open("PortMaster/pugwash", "w") as fh:
        fh.write("\n".join(pugwash_data["all_data"]))
        fh.write("\n")


if __name__ == '__main__':
    main(sys.argv)
