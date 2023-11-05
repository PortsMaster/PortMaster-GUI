#!/bin/bash

./do_i18n.sh

python3 tools/pm_release.py beta "$@"

git add PortMaster/

git commit
