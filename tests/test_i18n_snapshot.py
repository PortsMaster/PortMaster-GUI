# SPDX-License-Identifier: MIT
#
# Moving code around must not add, lose or change any translatable strings.
#
# Regenerate (only when strings change on purpose):
#   PM_UPDATE_I18N_SNAPSHOT=1 pytest tests/test_i18n_snapshot.py

import os
import shutil
import subprocess

import pytest

from conftest import DATA_DIR, PM_DIR


SNAPSHOT_FILE = DATA_DIR / "msgids.txt"


def source_files():
    """The files do_i18n.sh extracts strings from."""
    pylibs = PM_DIR / "pylibs"
    files = [PM_DIR / "pugwash"]
    files += sorted(pylibs.glob("pug*.py"))

    for package in ("harbourmaster", "pugwash"):
        if (pylibs / package).is_dir():
            files += sorted((pylibs / package).rglob("*.py"))

    return files


def current_msgids():
    result = subprocess.run(
        ["xgettext", "-L", "Python", "--no-location", "--sort-output", "--omit-header", "-o", "-",
            *[str(f) for f in source_files()]],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    return result.stdout.decode("utf-8")


@pytest.mark.skipif(shutil.which("xgettext") is None, reason="xgettext not installed (gettext)")
def test_msgids_unchanged():
    if os.environ.get("PM_UPDATE_I18N_SNAPSHOT") == "1":
        SNAPSHOT_FILE.write_text(current_msgids())

    assert current_msgids() == SNAPSHOT_FILE.read_text()
