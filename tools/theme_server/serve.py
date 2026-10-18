#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# The theme preview server, from a checkout. It lives in PortMaster/pylibs/theme_server,
# which ships with PortMaster for the on-device editor; see THEME.md and serve.py there.
#
#   python3 tools/theme_server/serve.py --themes DIR [--port 8090]
#   python3 tools/theme_server/serve.py --themes DIR --export OUT [...]

import sys
from pathlib import Path

PM_DIR = Path(__file__).resolve().parents[2] / "PortMaster"
sys.path[:0] = [str(PM_DIR / "pylibs"), str(PM_DIR / "exlibs")]

from theme_server.serve import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
