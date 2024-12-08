#!/usr/bin/env python3
#
# SPDX-License-Identifier: MIT
#

import datetime
import hashlib
import json
import sys


DOWNLOAD_URL = "https://github.com/PortsMaster/PortMaster-GUI/releases/download"

def hash_file(file_name):
    md5_obj = hashlib.md5()

    with open(file_name, 'rb') as fh:
        for data in iter(lambda: fh.read(4096), b''):
            md5_obj.update(data)

    return md5_obj.hexdigest()


def main(argv):
    updates = {
        "stable": ("stable", "beta", "alpha", ),
        "beta":   ("beta", "alpha", ),
        "alpha":  ("alpha", ),
        }

    md5sum = hash_file("PortMaster.zip")

    if len(argv) == 1:
        release_type = "alpha"
        version_number = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d-%H%M")

    elif len(argv) == 2:
        release_type = argv[1]
        version_number = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d-%H%M")

    else:
        release_type = argv[1]
        version_number = argv[2]

    with open("version.json", "r") as fh:
        version_data = json.load(fh)

    for update in updates[release_type]:
        version_data[update]['md5'] = md5sum
        version_data[update]['version'] = version_number
        version_data[update]['url'] = f"{DOWNLOAD_URL}/{version_number}/PortMaster.zip"

    with open("version.json", "w") as fh:
        json.dump(version_data, fh, indent=4)

    with open("version", "w") as fh:
        print(version_data['beta']['version'], file=fh)

if __name__ == '__main__':
    main(sys.argv)
