# SPDX-License-Identifier: MIT
#
# Per CFW hooks. HM_PLATFORMS maps the lowercase CFW name to its Platform class.

from .base import (
    SPECIAL_GAMELIST_CODE,
    PlatformBase,
    PlatformGCD_PortMaster,
    PlatformTesting,
    )
from .emuelec import (
    PlatformUOS,
    PlatformAmberELEC,
    PlatformEmuELEC,
    )
from .jelos import (
    PlatformJELOS,
    PlatformROCKNIX,
    )
from .batocera import (
    PlatformBatocera,
    PlatformREGLinux,
    PlatformKnulli,
    )
from .arkos import (
    PlatformArkOS,
    PlatformdArkOS,
    )
from .retrodeck import (
    PlatformRetroDECK,
    )
from .muos import (
    PlatformmuOS,
    )
from .trimui import (
    PORT_CONFIG_JSON,
    PlatformTrimUI,
    )
from .miyoo import (
    PlatformMiyoo,
    PlatformSpruce,
    )


HM_PLATFORMS = {
    'arkos':     PlatformArkOS,
    'arkos wummle': PlatformArkOS,
    'arkos aeux': PlatformArkOS,
    'darkos':    PlatformdArkOS,
    'darkosre':  PlatformdArkOS,
    'amberelec': PlatformAmberELEC,
    'emuelec':   PlatformEmuELEC,
    'unofficialos': PlatformUOS,
    'jelos':     PlatformJELOS,
    'rocknix':   PlatformROCKNIX,
    'batocera':  PlatformBatocera,
    'reglinux':  PlatformREGLinux,
    'knulli':    PlatformKnulli,
    'muos':      PlatformmuOS,
    'miyoo':     PlatformMiyoo,
    'trimui':    PlatformTrimUI,
    'spruce':    PlatformSpruce,
    'retrodeck': PlatformRetroDECK,
    'darwin':    PlatformTesting,
    'default':   PlatformBase,
    # 'default': PlatformAmberELEC,
    }


__all__ = (
    'PlatformBase',
    'HM_PLATFORMS',
    )
