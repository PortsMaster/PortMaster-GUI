# SPDX-License-Identifier: MIT
#
# Translations, in PortMaster/pylibs/locales, two files per language:
#
#   <lang>.json          {"English text": "translation", ...}   the code's _("...") strings
#   <lang>.themes.json   {"English text": "translation", ...}   themes' "text" values
#
# A string with no translation shows in English. strings.json and strings.themes.json
# list every string and where it's used (tools/i18n.py extract keeps them in step with
# the code and the themes); the theme server's translation editor edits the language files.

import json
import string
from pathlib import Path


LANGUAGE = None
_messages = {}
_themes = {}
_theme_own = {}


def _(text):
    """The translation of a string from the code, or the string itself."""
    return _messages.get(text) or text


def theme_text(text):
    """The translation of a theme's "text": the theme's own #translations first, then
    PortMaster's."""
    return _theme_own.get(text) or _themes.get(text) or text


DOMAINS = ('messages', 'themes')


def language_file(locales_dir, lang, domain='messages'):
    """locales/<lang>.json, or <lang>.themes.json for the themes' strings."""
    return Path(locales_dir) / (f"{lang}.json" if domain == 'messages' else f"{lang}.{domain}.json")


def _read(path):
    try:
        with open(str(path), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}

    if not isinstance(data, dict):
        return {}

    return {key: value for key, value in data.items() if isinstance(key, str) and isinstance(value, str) and value}


def _fields(text):
    """The names of a string's {fields}, as str.format reads them. Raises ValueError for a stray { or }."""
    return {field.split('.', 1)[0].split('[', 1)[0] for _, field, _, _ in string.Formatter().parse(text) if field is not None}


def safe_translation(text, translation):
    """
    The code calls .format() on what _() returns: a translation with a {field} the English
    doesn't have, or a stray { or }, would raise there (and stop PortMaster).
    """
    try:
        english = _fields(text)
    except ValueError:
        ## Not a format string, so nothing formats it.
        return True

    try:
        return _fields(translation) <= english
    except ValueError:
        return False


def read_language(locales_dir, lang):
    """
    {'messages': {...}, 'themes': {...}} for a language, empty where a file can't be read. A
    translation that would break .format() is left out: that string shows in English.
    """
    data = {domain: _read(language_file(locales_dir, lang, domain)) for domain in DOMAINS}
    data['messages'] = {text: translation for text, translation in data['messages'].items() if safe_translation(text, translation)}
    return data


def load_language(locales_dir, lang):
    """Use this language from now on."""
    global LANGUAGE, _messages, _themes
    data = read_language(locales_dir, lang)
    LANGUAGE = lang
    _messages, _themes = data['messages'], data['themes']


def set_theme_translations(translations):
    """A theme's own "#translations" ({lang: {text: translation}}) for the current language."""
    global _theme_own
    own = translations.get(LANGUAGE, {}) if isinstance(translations, dict) and LANGUAGE else {}
    _theme_own = {key: value for key, value in own.items() if isinstance(key, str) and isinstance(value, str) and value} if isinstance(own, dict) else {}


__all__ = (
    '_',
    'theme_text',
    'load_language',
    'read_language',
    'safe_translation',
    'language_file',
    'DOMAINS',
    'set_theme_translations',
    )
