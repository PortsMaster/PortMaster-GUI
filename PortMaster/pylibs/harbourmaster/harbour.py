# SPDX-License-Identifier: MIT

import json
import pathlib
import shutil
from pathlib import Path
from harbourmaster.i18n import _
from loguru import logger
from .config import HM_PORTS_DIR, HM_SCRIPTS_DIR, HM_SOURCE_DEFAULTS, HM_TESTING, HM_TOOLS_DIR
from .hardware import device_info
from .util import Callback, json_load_dict, json_safe_load
from .source import HM_SOURCE_APIS
from .platform import HM_PLATFORMS
from .hm_info import InfoMixin
from .hm_ports import PortsMixin
from .hm_featured import FeaturedMixin
from .hm_install import InstallMixin
from .hm_runtimes import RuntimesMixin


class HarbourMaster(InfoMixin, PortsMixin, FeaturedMixin, InstallMixin, RuntimesMixin):
    """
    The PortMaster engine. Its methods are spread over the mixins in hm_*.py, grouped by job.
    """
    _PORTS_INFO = None
    _PORTS_DOWNLOAD = None
    _PORTERS = None

    CONFIG_VERSION = 2
    DEFAULT_CONFIG = {
        'version': CONFIG_VERSION,
        'first-run': True,
        'ports_info_checked': None,
        'porters_checked': None,
        'show_experimental': False,
        }

    INFO_CHECK_INTERVAL = (60 * 60 * 1)

    # Where the official sources moved to when they became PortMasterV3.
    LEGACY_SOURCE_URLS = {
        'PortMaster':            "https://github.com/PortsMaster/PortMaster-New/releases/latest/download/ports.json",
        'PortMaster Multiverse': "https://github.com/PortsMaster-MV/PortMaster-MV-New/releases/latest/download/ports.json",
        }

    # This is the new way of checking files.
    PORT_INFO_JSON = "https://api.github.com/repos/PortsMaster/PortMaster-Info/git/trees/main?recursive=true"
    PORT_INFO_URL  = "https://github.com/PortsMaster/PortMaster-Info/raw/main/"
    # PORTS_INFO_URL          = PORT_INFO_URL + "ports_info.json"
    # FEATURED_PORTS_URL      = PORT_INFO_URL + "featured_ports.json"
    # FEATURED_IMAGES_ZIP_URL = PORT_INFO_URL + "featured_images.zip"
    # PORTERS_URL             = PORT_INFO_URL + "porters.json"
    # SOURCES_URL             = PORT_INFO_URL + "sources.json"

    def __init__(self, config, *, tools_dir=None, ports_dir=None, scripts_dir=None, temp_dir=None, callback=None):
        """
        config = load_config()
        """
        self._PORT_INFO_CACHE = {}

        if tools_dir is None:
            tools_dir = HM_TOOLS_DIR

        if ports_dir is None:
            ports_dir = HM_PORTS_DIR

        if scripts_dir is None:
            scripts_dir = HM_SCRIPTS_DIR

        if isinstance(tools_dir, str):
            tools_dir = Path(tools_dir)
        elif not isinstance(tools_dir, pathlib.PurePath):
            raise ValueError('tools_dir')

        if isinstance(ports_dir, str):
            ports_dir = Path(ports_dir)
        elif not isinstance(ports_dir, pathlib.PurePath):
            raise ValueError('ports_dir')

        if callback is None:
            callback = Callback()

        self.temp_dir   = temp_dir
        self.tools_dir  = tools_dir
        self.cfg_dir    = tools_dir / "PortMaster" / "config"
        self.libs_dir   = tools_dir / "PortMaster" / "libs"
        self.themes_dir = tools_dir / "PortMaster" / "themes"
        self.ports_dir  = ports_dir
        self.scripts_dir   = scripts_dir
        self.cfg_file      = self.cfg_dir / "config.json"
        self.runtimes_file = self.cfg_dir / "runtimes.json"
        self.need_restart  = False

        ## Why the last install_port failed, for autoinstall's summary.
        self.last_install_error = None

        self.sources = {}
        self.config = {
            'no-check': config.get('no-check', False),
            'offline': config.get('offline', False),
            'quiet': config.get('quiet', False),
            'debug': config.get('debug', False),
            }

        self.device = device_info()

        if self.device['name'].lower() in HM_PLATFORMS:
            self.platform = HM_PLATFORMS[self.device['name'].lower()](self)
            self.platform_name = self.device['name'].lower()
        else:
            self.platform = HM_PLATFORMS['default'](self)
            self.platform_name = 'default'

        self.callback = callback
        self.ports = []
        self.utils = []

        self._port_attrs_updated = True

        self.ports_dir.mkdir(0o755, parents=True, exist_ok=True)
        self.scripts_dir.mkdir(0o755, parents=True, exist_ok=True)
        self.themes_dir.mkdir(0o755, parents=True, exist_ok=True)
        self.libs_dir.mkdir(0o755, parents=True, exist_ok=True)

        with self.callback.enable_messages():
            self.callback.message(_("Loading..."))

            ## Missing or broken (cut off by a power off while saving): start afresh.
            self.cfg_data = json_load_dict(self.cfg_file, self.DEFAULT_CONFIG)

            if self.cfg_data.get('first-run', True) or not self.cfg_dir.is_dir():
                self.cfg_dir.mkdir(0o755, parents=True, exist_ok=True)

                for source_name in HM_SOURCE_DEFAULTS:
                    with (self.cfg_dir / source_name).open('w') as fh:
                        fh.write(HM_SOURCE_DEFAULTS[source_name])

            if self.cfg_data.get('first-run', True):
                self.platform.first_run()

                self.cfg_data['first-run'] = False

            if not HM_TESTING and (self.tools_dir / "PortMaster" / 'post-install').is_file():
                (self.tools_dir / "PortMaster" / 'post-install').unlink()
                self.platform.portmaster_post_install()

            if 'theme' not in self.cfg_data:
                self.cfg_data['theme'] = 'default_theme'

            self.cfg_data.setdefault('show_experimental', False)

            if self.cfg_data.get('version', 1) != self.CONFIG_VERSION:
                self.update_config()
                self.cfg_data['version'] = self.CONFIG_VERSION

            self.load_info()

            self.load_sources()

            self.load_ports()

            self.platform.loaded()

            self.save_config()

    def update_config(self):
        version = self.cfg_data.get('version', 1)
        if version:
            # Upgrade from version 1 to 2
            logger.debug(f"Upgrading PortMaster/config/config.json: 1 -> 2")

            for image_dir in self.cfg_dir.glob("images_*"):
                if not image_dir.is_dir():
                    continue

                logger.debug(f"rmtree {image_dir}")
                shutil.rmtree(str(image_dir))

            for source_file in self.cfg_dir.glob("*portmaster*.source.json"):
                if not source_file.is_file():
                    continue

                logger.debug(f"unlink {source_file}")
                source_file.unlink()

            for source_name in HM_SOURCE_DEFAULTS:
                with (self.cfg_dir / source_name).open('w') as fh:
                    fh.write(HM_SOURCE_DEFAULTS[source_name])

                logger.debug(f"creating {source_name}")

            version = 2

    def save_config(self):
        with open(self.cfg_file, 'w') as fh:
            json.dump(self.cfg_data, fh, indent=4, sort_keys=True)

        with open(self.runtimes_file, 'w') as fh:
            json.dump(self.runtimes_info, fh, indent=4, sort_keys=True)

    def load_sources(self):
        source_files = list(self.cfg_dir.glob('*.source.json'))
        source_files.sort()

        self._port_attrs_updated = True

        self.callback.message("  - {}".format(_("Loading Sources.")))

        check_keys = {'version': None, 'prefix': None, 'api': HM_SOURCE_APIS, 'name': None, 'last_checked': None, 'data': None}
        for source_file in source_files:
            with source_file.open() as fh:
                source_data = json_safe_load(fh)

            if source_data is None:
                continue

            # Sources from before PortMasterV3: only the official ones still exist, point them at the V3 urls.
            if source_data.get('api') in ('PortMasterV1', 'PortMasterV2') and source_data.get('name') in self.LEGACY_SOURCE_URLS:
                source_data['api'] = 'PortMasterV3'
                source_data['url'] = self.LEGACY_SOURCE_URLS[source_data['name']]
                source_data['last_checked'] = None
                source_data['data'] = {}

            fail = False
            for check_key, check_value in check_keys.items():
                if check_key not in source_data:
                    logger.error(f"Missing key {check_key!r} in {source_file}.")
                    fail = True
                    break

                if check_value is not None and source_data[check_key] not in check_value:
                    logger.error(f"Unknown {check_key!r} in {source_file}: {source_data[check_key]}.")
                    fail = True
                    break

            if fail:
                continue

            source = HM_SOURCE_APIS[source_data['api']](self, source_file, source_data)

            self.sources[source_data['prefix']] = source

    def set_gcd_mode(self, mode='standard'):
        self.platform.set_gcd_mode(mode)

    def get_gcd_mode(self):
        return self.platform.get_gcd_mode()

    def get_gcd_modes(self):
        return self.platform.get_gcd_modes()

__all__ = (
    'HarbourMaster',
    )
