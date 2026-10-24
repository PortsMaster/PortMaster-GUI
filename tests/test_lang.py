# SPDX-License-Identifier: MIT
#
# Picking the language (pugwash.lang): the system's from the environment, the one chosen in
# Options from config.json, switching at runtime, and the list of languages to choose from.
# Plus harbourmaster.i18n's lookups: code strings, theme text and a theme's own translations.

import json
import os

import pytest

from harbourmaster import i18n


@pytest.fixture
def lang(pugwash, monkeypatch, tmp_path):
    """pugwash.lang, put back as it was (module state, the environment, the translations)."""
    from pugwash import lang

    for key in ('LANG', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES'):
        monkeypatch.delenv(key, raising=False)
    for name in ('DEFAULT_LANG', 'CURRENT_LANG', 'ENVIRON_KEY'):
        monkeypatch.setattr(lang, name, getattr(lang, name))

    ## load_lang() reads the language chosen in Options from here.
    import harbourmaster
    tools = tmp_path / "tools"
    (tools / "PortMaster" / "config").mkdir(parents=True)
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", tools)
    monkeypatch.setattr(lang, "config_file", tools / "PortMaster" / "config" / "config.json", raising=False)

    yield lang

    i18n.load_language(lang.LANG_DIR, "en_US")
    i18n.set_theme_translations({})


def load(lang, config=None, **environ):
    if config is not None:
        lang.config_file.write_text(json.dumps(config) if not isinstance(config, str) else config)
    for key, value in environ.items():
        os.environ[key] = value
    lang.load_lang()
    return lang.DEFAULT_LANG, lang.CURRENT_LANG


################################################################################
## check_lang: a language PortMaster has, from whatever the system says
@pytest.mark.parametrize("value, expected", [
    ("de_DE", "de_DE"),
    ("de_DE.UTF-8", "de_DE"),
    ("de_DE.utf8", "de_DE"),
    (" de_DE ", "de_DE"),
    ("de", "de_DE"),
    ("de_AT", "de_DE"),
    ("en_AU.UTF-8", "en_US"),
    ("pt", "pt_BR"),          ## pt_PT has no translation, so the next pt_*
    ("zh_CN", "zh_CN"),
    ("ja_JP.eucJP", "ja_JP"),
    ])
def test_check_lang(lang, value, expected):
    assert lang.check_lang(value) == expected


@pytest.mark.parametrize("value", [
    None, "", " ", ".UTF-8", "_US", "_", ".", "C", "C.UTF-8", "POSIX", "zz_ZZ", "xx", 5, ["de_DE"]])
def test_check_lang_nothing(lang, value):
    ## "" (some CFWs set LANG to it) matched the first language there is: German.
    assert lang.check_lang(value) is None


################################################################################
## load_lang: config.json's language, else the system's, else English
def test_system_language(lang):
    assert load(lang, LANG="fr_FR.UTF-8") == ("fr_FR", "fr_FR")
    assert os.environ['LANG'] == "fr_FR"


def test_chosen_language_wins(lang):
    assert load(lang, {"language": "ja_JP"}, LANG="fr_FR.UTF-8") == ("fr_FR", "ja_JP")


@pytest.mark.parametrize("config", [{"language": "zz_ZZ"}, {"language": ""}, {"language": None}, {}, "{ not json", "null"])
def test_bad_chosen_language_is_the_systems(lang, config):
    assert load(lang, config, LANG="de_DE") == ("de_DE", "de_DE")


@pytest.mark.parametrize("value", ["", "C", "POSIX", "zz_ZZ"])
def test_no_usable_system_language_is_english(lang, value):
    ## DEFAULT_LANG too: with LANG="" it was German, so choosing German "reset" to English.
    assert load(lang, LANG=value) == ("en_US", "en_US")


def test_no_language_variable_at_all(lang):
    assert load(lang) == ("en_US", "en_US")
    assert lang.ENVIRON_KEY == "LANG" and os.environ["LANG"] == "en_US"


def test_first_language_variable_is_used(lang):
    ## LANG first: the others are dropped, so ports PortMaster starts see one language.
    assert load(lang, LANG="it_IT", LANGUAGE="de_DE", LC_ALL="fr_FR") == ("it_IT", "it_IT")
    assert "LANGUAGE" not in os.environ and "LC_ALL" not in os.environ


def test_other_language_variable(lang):
    assert load(lang, LC_ALL="ru_RU.UTF-8") == ("ru_RU", "ru_RU")
    assert lang.ENVIRON_KEY == "LC_ALL" and os.environ["LC_ALL"] == "ru_RU"


################################################################################
## set_language: switching while PortMaster runs
def test_set_language(lang):
    load(lang, LANG="en_US")

    assert lang.set_language("de_DE") == "de_DE"
    assert lang.CURRENT_LANG == "de_DE" and os.environ[lang.ENVIRON_KEY] == "de_DE"
    assert i18n._("Options") == "Optionen"

    ## None, or one PortMaster hasn't: the system's.
    for value in (None, "zz_ZZ", ""):
        assert lang.set_language(value) == "en_US"
        assert i18n._("Options") == "Options"


def test_set_language_simplifies(lang):
    load(lang, LANG="en_US")
    assert lang.set_language("ja_JP.UTF-8") == "ja_JP"
    assert i18n._("Options") == "オプション"


################################################################################
## The language list
def test_lang_list_has_the_languages_with_a_translation(lang):
    load(lang, LANG="en_US")
    listed = lang.lang_list()

    files = {path.name[:-5] for path in lang.LANG_DIR.glob("??_??.json")}
    assert set(listed) == files
    ## Sorted by name, in English.
    assert list(listed.values()) == sorted(listed.values())
    assert listed["de_DE"] == "German" and listed["ja_JP"] == "Japanese"


def test_lang_list_in_the_current_language(lang):
    load(lang, LANG="en_US")
    lang.set_language("de_DE")
    listed = lang.lang_list()

    assert listed["de_DE"] == "Deutsch" and listed["en_US"] == "Englisch"
    assert list(listed.values()) == sorted(listed.values())


def test_every_translation_is_a_listed_language(lang):
    ## A language file without an ALL_LANGUAGES entry could never be chosen.
    files = {path.name[:-5] for path in lang.LANG_DIR.glob("??_??.json")}
    assert files <= set(lang.ALL_LANGUAGES)


def test_every_language_names_every_language(lang):
    ## The list is in the current language: each one has a name for all of them.
    load(lang, LANG="en_US")
    files = sorted(path.name[:-5] for path in lang.LANG_DIR.glob("??_??.json"))
    english = {code: name for code, name in lang.ALL_LANGUAGES.items() if code in files}

    for code in files:
        if code == "en_US":
            continue
        lang.set_language(code)
        names = lang.lang_list()
        untranslated = [name for listed, name in names.items() if name == english[listed]]
        assert untranslated == [], f"{code}: {untranslated}"


################################################################################
## harbourmaster.i18n lookups
@pytest.fixture
def locales(tmp_path):
    (tmp_path / "xx_XX.json").write_text(json.dumps({"Options": "Opzioni", "Empty": "", "Bad": 5}))
    (tmp_path / "xx_XX.themes.json").write_text(json.dumps({"Genres:": "Generi:"}))
    yield tmp_path
    i18n.load_language(tmp_path.parent, "en_US")
    i18n.set_theme_translations({})


def test_i18n_lookups(locales):
    i18n.load_language(locales, "xx_XX")

    assert i18n.LANGUAGE == "xx_XX"
    assert i18n._("Options") == "Opzioni"
    ## Empty or not a string: the English.
    assert i18n._("Empty") == "Empty" and i18n._("Bad") == "Bad"
    assert i18n.theme_text("Genres:") == "Generi:"
    ## Code and theme strings are separate.
    assert i18n.theme_text("Options") == "Options" and i18n._("Genres:") == "Genres:"


def test_theme_translations_come_first(locales):
    i18n.load_language(locales, "xx_XX")
    i18n.set_theme_translations({"xx_XX": {"Genres:": "Tipi:", "Empty": ""}, "yy_YY": {"Genres:": "Nope"}})

    assert i18n.theme_text("Genres:") == "Tipi:"
    assert i18n.theme_text("Empty") == "Empty"

    ## A language switch keeps the theme's, for the new language.
    i18n.load_language(locales, "yy_YY")
    i18n.set_theme_translations({"xx_XX": {"Genres:": "Tipi:"}, "yy_YY": {"Genres:": "Nope"}})
    assert i18n.theme_text("Genres:") == "Nope"


@pytest.mark.parametrize("translations", [None, [], "x", {"xx_XX": "not a dict"}, {"xx_XX": {"a": 5, 5: "b"}}])
def test_bad_theme_translations(locales, translations):
    ## From a theme's "#translations": whatever is in there.
    i18n.load_language(locales, "xx_XX")
    i18n.set_theme_translations(translations)
    assert i18n.theme_text("Genres:") == "Generi:" and i18n.theme_text("a") == "a"


@pytest.mark.parametrize("contents", ["[]", '"x"', "null", "{ not json", "\xff\xfe"])
def test_bad_language_file(locales, contents):
    (locales / "zz_ZZ.json").write_bytes(contents.encode("latin-1"))
    i18n.load_language(locales, "zz_ZZ")
    assert i18n._("Options") == "Options"


def test_missing_language_file(locales):
    i18n.load_language(locales, "qq_QQ")
    assert i18n.LANGUAGE == "qq_QQ" and i18n._("Options") == "Options"


def test_language_file_names(tmp_path):
    assert i18n.language_file(tmp_path, "de_DE").name == "de_DE.json"
    assert i18n.language_file(tmp_path, "de_DE", "themes").name == "de_DE.themes.json"
