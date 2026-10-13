# SPDX-License-Identifier: MIT
#
# Startup: argument parsing, logging, and running the GUI or fifo_control.

import sys
from harbourmaster import console
import harbourmaster
from loguru import logger
from pugwash.scenes import BlankScene
from harbourmaster import HarbourMaster, make_temp_directory
from gettext import gettext as _
from pugwash import PORTMASTER_DEBUG
from pugwash.app import PortMasterGUI
from pugwash.update import portmaster_check_update
from pugwash.util import get_ip_address


################################################################################
## Logging
LOG_FILE = harbourmaster.HM_TOOLS_DIR / "PortMaster" / "pugwash.txt"
LOG_FILE_HANDLE = None
if LOG_FILE.parent.is_dir():
    LOG_FILE_HANDLE = logger.add(LOG_FILE, level="DEBUG", backtrace=True, diagnose=True)


@logger.catch
def main(argv):
    global LOG_FILE_HANDLE
    global LOG_FILE

    with make_temp_directory() as temp_dir:
        argv = argv[:]

        config = {
            'quiet': False,
            'no-check': False,
            'debug': False,
            'no-colour': False,
            'force-colour': False,
            'no-log': False,
            'help': False,
            'offline': False,
            'no-harbour': False,
            }

        i = 1
        while i < len(argv):
            if argv[i] == '--':
                del argv[i]
                break

            if argv[i].startswith('--'):
                if argv[i][2:] in config:
                    config[argv[i][2:]] = True
                else:
                    if not config['quiet']:
                        logger.error(f"Unknown argument {argv}")

                del argv[i]
                continue

            i += 1

        if (harbourmaster.HM_TOOLS_DIR / "PortMaster" / "debug_all_the_things_flag").is_file():
            config['debug'] = True

        if config['quiet']:
            logger.remove(0)  # For the default handler, it's actually '0'.
            logger.add(sys.stderr, level="ERROR")

        elif config['debug']:
            logger.remove(0)  # For the default handler, it's actually '0'.
            logger.add(sys.stderr, level="DEBUG")

        elif not PORTMASTER_DEBUG:
            logger.remove(0)  # For the default handler, it's actually '0'.
            logger.add(sys.stderr, level="SUCCESS")

            ## Once we reach here we can just reduce it to INFO level.
            logger.remove(LOG_FILE_HANDLE)
            LOG_FILE_HANDLE = logger.add(LOG_FILE, level="INFO", backtrace=True, diagnose=True)

        if config['no-log']:
            logger.remove(LOG_FILE_HANDLE)
            LOG_FILE_HANDLE = None

        if config['no-colour']:
            console.do_color(False)

        elif config['force-colour']:
            console.do_color(True)

        if not get_ip_address():
            config['offline'] = True
            logger.warning("No internet connection found, running in offline mode.")

        if len(argv) > 1 and argv[1] == "fifo_control":
            pm = PortMasterGUI(first_scene=BlankScene, force_theme="default_theme")
            pm.hm = None

            if not config['no-harbour']:
                with pm.enable_cancellable(False):
                    pm.hm = pm.run_task(HarbourMaster, config, temp_dir=temp_dir, callback=pm)

            if pm.hm is not None:
                if pm.hm.platform.WANT_XBOX_FIX:
                    pm.events.fix_xbox_mode()

                pm.SWAP_BUTTONS = pm.hm.platform.WANT_SWAP_BUTTONS

            pm.do_fifo_control(config, argv[2:])
            pm.quit()
            return 0

        pm = PortMasterGUI()
        pm.hm = None

        if not harbourmaster.HM_TESTING and not config['no-check']:
            if portmaster_check_update(pm, config, temp_dir):
                pm.quit()
                return 0

        with pm.enable_cancellable(False):
            pm.hm = pm.run_task(HarbourMaster, config, temp_dir=temp_dir, callback=pm)

        reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
        if not reboot_file.is_file():
            with pm.enable_cancellable(True):
                pm.run()

        if not harbourmaster.HM_TESTING:
            logger.debug(f"{pm.hm}: {pm.hm.platform.ES_NAME}")
            if pm.hm is not None and pm.hm.platform.ES_NAME is not None:
                logger.debug(f"{pm.hm.platform.ports_changed()}")
                if pm.hm.platform.ports_changed():
                    if pm.hm.platform.ES_NAME == 'show-refresh':
                        pm.message_box(_("Ports have been added or removed, update your games list to see the new games or remove the uninstalled ones." + pm.hm.platform.ROMS_REFRESH_TEXT))
                    else:
                        pm.request_frontend_refresh()

        # if harbourmaster.HM_TESTING:
        #     for key, value in pm.text_data.items():
        #         print(f"- {key}: {value}")

        pm.quit()

        return 0
