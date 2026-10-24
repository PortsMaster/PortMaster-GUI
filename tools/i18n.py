#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# PortMaster's translatable strings: the code is in PortMaster/pylibs/theme_server/translations.py.
#
#   python3 -I tools/i18n.py extract [--themes DIR]
#   python3 -I tools/i18n.py check

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "PortMaster" / "pylibs"))

from theme_server.translations import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
