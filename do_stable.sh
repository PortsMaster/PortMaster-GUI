#!/bin/bash
#
# SPDX-License-Identifier: MIT
#

./do_i18n.sh

python3 tools/pm_release.py stable "$@"

git add PortMaster/

git commit
