# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Finding resource files (themes, fonts, images) on the resource paths.

import functools
import pathlib
from pathlib import Path
from .errors import GUIValueError


class ResourceManager:
    def __init__(self, gui):
        self.gui = gui
        self._paths = []

    def add_path(self, path):
        if isinstance(path, pathlib.PurePath):
            pass
        elif isinstance(path, str):
            path = Path(path)
        else:
            raise GUIValueError(f"Invalid {path!r}")

        # print(path)
        if not path.is_dir():
            return

        if path not in self._paths:
            self._paths.append(path)
            self.find.cache_clear()

    def remove_path(self, path):
        if isinstance(path, pathlib.PurePath):
            pass
        elif isinstance(path, str):
            path = Path(path)
        else:
            raise GUIValueError(f"Invalid {path!r}")

        if path in self._paths:
            self._paths.remove(path)
            self.find.cache_clear()

    @staticmethod
    def _is_file(path):
        ## Theme values that are text ("Zurück" on a button bar) get looked up too; a name the
        ## filesystem refuses (EPERM on exFAT for one that isn't UTF-8) is just not a file.
        try:
            return path.is_file()
        except (OSError, ValueError):
            return False

    @functools.lru_cache(512)
    def find(self, file_name):
        if isinstance(file_name, pathlib.PurePath):
            pass

        elif isinstance(file_name, str):
            file_name = Path(file_name)

        elif file_name is None:
            return None

        else:
            raise GUIValueError(f"Invalid {file_name!r}")

        if file_name.name in ('.', '..'):
            return None

        if self._is_file(file_name):
            return file_name

        for path in reversed(self._paths):
            full_file_name = path / file_name

            if self._is_file(full_file_name):
                return full_file_name

        return None
