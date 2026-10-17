# SPDX-License-Identifier: MIT
#
# Translations: picks the language and sets up gettext when imported.

import gettext
import os
import harbourmaster
from gettext import gettext as _
from pugwash import PYLIB_PATH


################################################################################
## Translations
LANG_DIR = PYLIB_PATH / "locales"
## Set by load_lang().
DEFAULT_LANG = None
CURRENT_LANG = None


ALL_LANGUAGES = {
    ## Keep it in order of importance, for example pt_PT before pt_BR.
    "da_DK": _("Danish"),
    "de_DE": _("German"),
    "en_US": _("English"),
    "es_ES": _("Spanish"),
    "eo_UY": _("Esperanto"),
    "fi_FI": _("Finnish"),
    "fr_FR": _("French"),
    "it_IT": _("Italian"),
    "ja_JP": _("Japanese"),
    "ko_KR": _("Korean"),
    "nl_NL": _("Dutch"),
    "pl_PL": _("Polish"),
    "pt_PT": _("Portuguese (Portugal)"),
    "pt_BR": _("Portuguese (Brazil)"),
    "ro_RO": _("Romanian"),
    "ru_RU": _("Russian"),
    "sv_SE": _("Swedish"),
    "uk_UA": _("Ukrainian"),
    "zh_CN": _("Chinese Simplified"),
    }


def check_lang(lang):
    """
    Check if `LANG_DIR / lang / "LC_MESSAGES"` exists

    We simplify the language by removing any encoding eg: `en_AU.utf8` to `en_AU`
    We then simplify the language by removing any sub-language: `en_AU` to `en`

    We then check all languages on the list of languages.
    """
    if lang is None:
        return None

    temp = LANG_DIR / lang / "LC_MESSAGES"
    if temp.is_dir():
        return lang

    if '.' in lang:
        lang = lang.rsplit('.', 1)[0]

        temp = LANG_DIR / lang / "LC_MESSAGES"
        if temp.is_dir():
            return lang

    if '_' in lang:
        lang = lang.split('_', 1)[0]

    for lang_opt in ALL_LANGUAGES:
        temp = LANG_DIR / lang_opt / "LC_MESSAGES"
        if temp.is_dir() and lang_opt.startswith(lang):
            return lang_opt

    return None


def load_lang():
    """

    Load the desired language, we check for an override in our config.json, otherwise use the environment variables.

    """
    global DEFAULT_LANG, CURRENT_LANG


    config = harbourmaster.HM_TOOLS_DIR / "PortMaster" / "config" / "config.json"
    if config.is_file():
        with open(config, 'r') as fh:
            config = harbourmaster.json_safe_load(fh)

        if config is not None:
            config_lang = config.get("language", None)

        else:
            config_lang = None

    else:
        config_lang = None

    environ_key = None
    environ_lang = None
    for key in ('LANG', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES'):
        if key in os.environ:
            if environ_key is not None:
                del os.environ[key]

            else:
                environ_key = key
                environ_lang = os.environ[key]

    if environ_key is None:
        environ_key = 'LANG'

    DEFAULT_LANG = check_lang(environ_lang) or 'en_US'

    if config_lang and check_lang(config_lang):
        os.environ[environ_key] = check_lang(config_lang)

    elif environ_lang and check_lang(environ_lang):
        os.environ[environ_key] = check_lang(environ_lang)

    else:
        os.environ[environ_key] = 'en_US'

    CURRENT_LANG = os.environ[environ_key]


def lang_list():
    languages = {
        lang_id: lang_name
        for lang_id, lang_name in sorted(ALL_LANGUAGES.items(), key=lambda item: (item[1]))
        if (LANG_DIR / lang_id).is_dir()}

    return languages


load_lang()
gettext.bindtextdomain('messages', str(LANG_DIR))
gettext.bindtextdomain('themes', str(LANG_DIR))
gettext.textdomain('messages')
