# SPDX-License-Identifier: MIT
#
# Checking for and installing PortMaster updates.

import datetime
import json
import harbourmaster
from loguru import logger
from harbourmaster import HarbourMaster
from harbourmaster.i18n import _
from pugwash import PORTMASTER_VERSION, PORTMASTER_RELEASE_CHANNEL, PORTMASTER_MIN_VERSION, PORTMASTER_RELEASE_URL, PORTMASTER_RELEASE_VALUES, PORTMASTER_UPDATE_FREQUENCY


def portmaster_check_update(pm, config, temp_dir):
    cfg_dir = harbourmaster.HM_TOOLS_DIR / "PortMaster"

    cfg_file = cfg_dir / "config" / "config.json"
    cfg_data = {}

    if cfg_file.is_file():
        cfg_data = harbourmaster.json_load_dict(cfg_file)

    update_checked = cfg_data.get('update_checked', None)

    release_channel = cfg_data.setdefault('release_channel', PORTMASTER_RELEASE_CHANNEL)
    change_channel = cfg_data.setdefault('change_channel', False)

    if release_channel not in PORTMASTER_RELEASE_VALUES:
        release_channel = PORTMASTER_RELEASE_VALUES[-1]
        cfg_data['release_channel'] = release_channel

        with open(cfg_file, 'w') as fh:
            json.dump(cfg_data, fh, indent=4)

    if update_checked is None or harbourmaster.datetime_compare(update_checked) > PORTMASTER_UPDATE_FREQUENCY:
        update_checked_was_none = update_checked is None
        try:
            release_info = pm.run_task(harbourmaster.fetch_json, PORTMASTER_RELEASE_URL + 'version.json')

        except Exception as err:
            logger.error(f'Unable to download {PORTMASTER_RELEASE_URL}version.json: {err}')
            return None

        if release_info is None:
            # Whelp, we tried.
            logger.error(f'Unable to download {PORTMASTER_RELEASE_URL}version.json')
            return False

        channel_info = release_info.get(release_channel) if isinstance(release_info, dict) else None
        if not isinstance(channel_info, dict) or not all(isinstance(channel_info.get(key), str) for key in ('version', 'url', 'md5')):
            logger.error(f'Unable to find {release_channel} in {release_info!r}')
            # Whelp, we tried.
            return False

        latest_version = release_info[release_channel]['version']
        if harbourmaster.version_parse(latest_version) < harbourmaster.version_parse(PORTMASTER_MIN_VERSION):
            logger.info(f"PortMaster cannot downgrade to {latest_version}, minimum version is {PORTMASTER_MIN_VERSION}")
            return False

        logger.info(f"Checking for updates: {latest_version} vs {PORTMASTER_VERSION}")

        cfg_data['update_checked'] = datetime.datetime.now().isoformat()
        if not cfg_file.parent.is_dir():
            cfg_file.parent.mkdir(0o777, parents=True)

        with open(cfg_file, 'w') as fh:
            json.dump(cfg_data, fh, indent=4)

        update_ask = False
        update_reason = ""
        update_release = False

        VERSION_NEWER = harbourmaster.version_parse(latest_version) > harbourmaster.version_parse(PORTMASTER_VERSION)
        VERSION_OLDER = harbourmaster.version_parse(latest_version) < harbourmaster.version_parse(PORTMASTER_VERSION)

        if change_channel and VERSION_OLDER:
            update_release = True
            update_ask = True
            update_reason = _("You are switching from the {old_release_channel} to the {new_release_channel} version.\n\nDo you want to downgrade?").format(
                old_release_channel=PORTMASTER_RELEASE_CHANNEL,
                new_release_channel=release_channel)

        elif VERSION_NEWER:
            update_ask = True
            update_reason = _("There is a new version of PortMaster ({portmaster_version})\n\nDo you want to upgrade?").format(
                portmaster_version=latest_version)

        elif update_checked_was_none and cfg_data.get('konami', False):
            update_ask = True
            update_reason = _("Do you want to reinstall PortMaster?\n\nThis will reinstall from the {release_channel} channel to {portmaster_version}.").format(
                portmaster_version=latest_version,
                release_channel=release_channel)

        if update_ask:
            old_check = config['no-check']
            config['no-check'] = True

            pm.hm = pm.run_task(HarbourMaster, config, temp_dir=temp_dir, callback=pm)
            pm.apply_button_mapping()

            if pm.message_box(update_reason, want_cancel=True):
                pm.do_install(
                    "PortMaster",
                    release_info[release_channel]['url'],
                    allow_cancel=False,
                    md5_source=release_info[release_channel]['md5'])

                if change_channel:
                    pm.hm.cfg_data['change_channel'] = False
                    pm.hm.save_config()

                reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
                if not reboot_file.is_file():
                    reboot_file.touch(0o644)

                return True

            config['no-check'] = old_check
            pm.hm = None

    return False
