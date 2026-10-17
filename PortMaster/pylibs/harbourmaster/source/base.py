# SPDX-License-Identifier: MIT
#
# BaseSource, the interface every port source implements.

from gettext import gettext as _
from ..config import HM_UPDATE_FREQUENCY
from ..util import datetime_compare, name_cleaner


################################################################################
## APIS
class BaseSource():
    VERSION = 0

    def __init__(self, hm, file_name, config):
        self.hm = hm
        self._file_name = file_name
        self._config = config
        self._prefix = config['prefix']
        self._did_update = False
        self._wants_update = None
        self._images_dir = self.hm.cfg_dir / f"images_{self._prefix}"
        self._images_md5_file = self._images_dir / "images.md5"
        self._images_json_file = self._images_dir / "images.json"
        self._images_md5 = None

        if not self._images_dir.is_dir():
            self._images_dir.mkdir(0o777)

        if self._images_md5_file.is_file():
            self._images_md5 = self._images_md5_file.read_text().strip()

        if config['version'] != self.VERSION:
            self._wants_update = _("Cache out of date.")
            if config['version'] < 4:
                self._images_md5 = None

        elif self._config['last_checked'] is None:
            self._wants_update = _("First check.")

        elif datetime_compare(self._config['last_checked']) > HM_UPDATE_FREQUENCY:
            self._wants_update = _("Auto Update.")

        if not self.hm.config['no-check'] and not self.hm.config['offline']:
            self.auto_update()
        else:
            self.load()

    @property
    def name(self):
        return self._config['name']

    def auto_update(self):
        if self._wants_update is not None:
            # cprint(f"<b>{self._config['name']}</b>: {self._wants_update}")
            if self.hm.callback is not None:
                self.hm.callback.message(f" - {self._config['name']}: {self._wants_update}")

            self.update()
            self._wants_update = None

        else:
            self.load()

    def load(self):
        raise NotImplementedError()

    def save(self):
        raise NotImplementedError()

    def update(self):
        raise NotImplementedError()

    def clean_name(self, text):
        return name_cleaner(text)
