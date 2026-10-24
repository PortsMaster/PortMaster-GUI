# SPDX-License-Identifier: MIT
#
# The Edit view's files: reading and saving a theme's theme.json, drafts (unsaved text
# rendered from a copy of the theme made of links, so the preview follows the typing
# without touching the theme), and copying a theme to start a new one.
#
# Python 3.7, standard library only.

import hashlib
import json
import os
import re
import shutil
import threading
from pathlib import Path


MAX_THEME_SIZE = 4 * 1024 * 1024
DRAFT_SUFFIX = "~draft"
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _.()+-]{0,47}$')


class EditorError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


def text_version(data):
    return hashlib.sha1(data).hexdigest()[:16]


def check_text(text):
    """None if text is a theme.json PortMaster can load (a JSON object), else {'error', 'line', 'column'}."""
    try:
        data = json.loads(text)
    except ValueError as error:
        return {'error': getattr(error, 'msg', str(error)), 'line': getattr(error, 'lineno', None), 'column': getattr(error, 'colno', None)}
    if not isinstance(data, dict):
        return {'error': "theme.json has to be a JSON object: { ... }", 'line': 1, 'column': 1}
    return None


def rename_text(text, name):
    """theme.json's text with #info's name set to name, keeping its layout where it can."""
    data = json.loads(text)
    info = data.get("#info")
    match = re.search(r'"#info"\s*:\s*\{', text)
    if isinstance(info, dict) and match:
        ## Its "name" (the first one in #info, at #info's own depth).
        depth, index = 1, match.end()
        in_string = False
        while index < len(text) and depth > 0:
            char = text[index]
            if in_string:
                if char == "\\":
                    index += 1
                elif char == '"':
                    in_string = False
            elif char == '"':
                if depth == 1:
                    found = re.compile(r'"name"\s*:\s*"((?:[^"\\]|\\.)*)"').match(text, index)
                    if found:
                        new_text = text[:found.start(1)] + json.dumps(name)[1:-1] + text[found.end(1):]
                        if json.loads(new_text).get("#info", {}).get("name") == name:
                            return new_text
                in_string = True
            elif char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
            index += 1

    ## No name to change: written out again.
    if not isinstance(data.get("#info"), dict):
        data["#info"] = {}
    data["#info"]["name"] = name
    return json.dumps(data, indent=4, ensure_ascii=False) + "\n"


class ThemeEditor:
    """theme.json files of the server's themes (serve.Themes), and their drafts."""
    def __init__(self, themes, work_dir, default_theme_dir):
        self.themes = themes
        self.drafts_dir = Path(work_dir) / "drafts"
        self.default_theme_dir = Path(default_theme_dir).resolve()
        self.lock = threading.Lock()

    def _theme(self, theme_id):
        if not isinstance(theme_id, str) or theme_id.endswith(DRAFT_SUFFIX):
            raise EditorError(404, "no such theme")
        theme_dir = self.themes.get(theme_id)
        if theme_dir is None:
            raise EditorError(404, f"no theme {theme_id!r}")
        return Path(theme_dir)

    def writable(self, theme_dir):
        """Only the themes in --themes, never the built-in default theme."""
        theme_dir = Path(theme_dir).resolve()
        root = self.themes.themes_dir
        if root is None or theme_dir == self.default_theme_dir:
            return False
        if theme_dir != root and theme_dir.parent != root:
            return False
        return os.access(str(theme_dir), os.W_OK) and os.access(str(theme_dir / "theme.json"), os.W_OK)

    def copy_folder(self):
        """Where a copy goes: --themes, when it's a folder of themes."""
        root = self.themes.themes_dir
        if root is None or not root.is_dir() or (root / "theme.json").is_file() or not os.access(str(root), os.W_OK):
            return None
        return root

    def read(self, theme_id):
        theme_dir = self._theme(theme_id)
        try:
            data = (theme_dir / "theme.json").read_bytes()
        except OSError as error:
            raise EditorError(404, f"can't read theme.json: {error.strerror}")
        return {'theme': theme_id, 'text': data.decode("utf-8", "replace"), 'version': text_version(data),
                'writable': self.writable(theme_dir), 'can_copy': self.copy_folder() is not None,
                ## Downloaded from the theme list (it wrote theme.md5): updating it there replaces it.
                'downloaded': (theme_dir / "theme.md5").is_file()}

    def save(self, theme_id, text, version):
        """Writes theme.json (the old one becomes theme.json.bak) if it's still `version` on disk."""
        theme_dir = self._theme(theme_id)
        if not self.writable(theme_dir):
            raise EditorError(403, "this theme can't be changed here: copy it to a new theme first")
        data = text.encode("utf-8")
        if len(data) > MAX_THEME_SIZE:
            raise EditorError(413, "theme.json is too big")
        problem = check_text(text)
        if problem is not None:
            raise EditorError(400, f"not saved, it isn't valid JSON: {problem['error']}", **problem)

        theme_file = theme_dir / "theme.json"
        with self.lock:
            old = theme_file.read_bytes()
            if text_version(old) != version:
                ## Changed since the page loaded it (another editor, a copy from the PC).
                raise EditorError(409, "theme.json changed on disk since you opened it",
                                  text=old.decode("utf-8", "replace"), version=text_version(old))
            if old != data:
                (theme_dir / "theme.json.bak").write_bytes(old)
                temp = theme_dir / "theme.json.tmp"
                temp.write_bytes(data)
                os.replace(str(temp), str(theme_file))

        return {'ok': True, 'version': text_version(data)}

    def draft(self, theme_id, text):
        """The id of a theme that is this one with theme.json's text: for the preview, saving nothing."""
        theme_dir = self._theme(theme_id)
        data = text.encode("utf-8")
        if len(data) > MAX_THEME_SIZE:
            raise EditorError(413, "theme.json is too big")
        problem = check_text(text)
        if problem is not None:
            raise EditorError(400, problem['error'], **problem)

        draft_id = theme_id + DRAFT_SUFFIX
        draft_dir = self.drafts_dir / re.sub(r'[^A-Za-z0-9_.-]', "_", theme_id)
        with self.lock:
            self._mirror(theme_dir, draft_dir)
            draft_file = draft_dir / "theme.json"
            if not draft_file.is_file() or draft_file.read_bytes() != data:
                temp = draft_dir / "theme.json.tmp"
                temp.write_bytes(data)
                os.replace(str(temp), str(draft_file))
            self.themes.drafts[draft_id] = draft_dir

        return {'ok': True, 'theme': draft_id}

    @staticmethod
    def _mirror(theme_dir, draft_dir):
        """draft_dir: links to every file of theme_dir but theme.json (copies where links don't work)."""
        wanted = set()
        for root, dirs, files in os.walk(str(theme_dir)):
            dirs[:] = [name for name in dirs if name != "__pycache__"]
            for name in files:
                relative = os.path.relpath(os.path.join(root, name), str(theme_dir))
                if relative not in ("theme.json", "theme.json.bak", "theme.json.tmp"):
                    wanted.add(relative)

        draft_dir.mkdir(parents=True, exist_ok=True)
        for root, dirs, files in os.walk(str(draft_dir)):
            for name in files:
                relative = os.path.relpath(os.path.join(root, name), str(draft_dir))
                if relative not in wanted and relative != "theme.json":
                    os.unlink(os.path.join(root, name))

        for relative in sorted(wanted):
            source, target = theme_dir / relative, draft_dir / relative
            if os.path.lexists(str(target)):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.symlink(str(source.resolve()), str(target))
            except OSError:
                shutil.copy2(str(source), str(target))

    def copy(self, theme_id, name, text=None):
        """A new theme in --themes: a copy of this one, called name, with theme.json's text
        if it's given (the unsaved changes). Returns its id."""
        theme_dir = self._theme(theme_id)
        root = self.copy_folder()
        if root is None:
            raise EditorError(403, "there's no themes folder to copy it into")
        if not isinstance(name, str) or not NAME_RE.match(name.strip()):
            raise EditorError(400, "a name of letters, numbers, spaces and . _ - ( ) +, up to 48 long")
        name = name.strip()
        new_id = re.sub(r'\s+', "_", name)
        target = root / new_id
        if text is not None:
            problem = check_text(text) if isinstance(text, str) and len(text.encode("utf-8")) <= MAX_THEME_SIZE else {'error': "too big"}
            if problem is not None:
                raise EditorError(400, f"not copied, theme.json isn't valid JSON: {problem['error']}", **problem)
        if new_id.endswith(DRAFT_SUFFIX) or self.themes.get(new_id) is not None or os.path.lexists(str(target)):
            raise EditorError(409, f"there's a theme called {new_id!r} already")

        with self.lock:
            shutil.copytree(str(theme_dir), str(target),
                            ignore=shutil.ignore_patterns("__pycache__", "theme.json.bak", "theme.json.tmp", "theme.md5", "*.pyc"))
            try:
                if text is None:
                    text = (target / "theme.json").read_text(encoding="utf-8")
                (target / "theme.json").write_text(rename_text(text, name), encoding="utf-8")
            except (OSError, ValueError):
                ## A theme.json that doesn't load is copied as it is.
                pass

        return {'ok': True, 'theme': new_id}
