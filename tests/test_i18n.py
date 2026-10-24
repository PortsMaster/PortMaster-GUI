# SPDX-License-Identifier: MIT
#
# Translations: PortMaster/pylibs/locales/<lang>.json, read by harbourmaster.i18n, and the
# list of every translatable string, locales/strings.json (tools/i18n.py extract).

import json

import pytest

from conftest import PM_DIR

from harbourmaster import i18n

from theme_server import translations as i18n_tool


LOCALES_DIR = PM_DIR / "pylibs" / "locales"
LANGUAGES = i18n_tool.languages()


def test_strings_json_matches_the_code():
    ## Moving code around must not add, lose or change a translatable string without
    ## strings.json (what translators see) knowing. After changing strings on purpose:
    ##   python3 -I tools/i18n.py extract
    strings = i18n_tool.read_strings()
    code = i18n_tool.code_strings()
    assert sorted(code) == sorted(strings['messages']), "run: python3 -I tools/i18n.py extract"
    assert set(i18n_tool.theme_strings(PM_DIR / "pylibs" / "default_theme")) <= set(strings['themes'])


def test_extraction_finds_every_call(tmp_path):
    source = tmp_path / "example.py"
    source.write_text(
        'from harbourmaster.i18n import _\n'
        'a = _("Plain")\n'
        'b = _("Joined "\n'
        '      "together {name}").format(name=1)\n'
        'c = _(f"not {a}")\n'
        'd = other("Not this")\n')
    assert list(i18n_tool.code_strings([source])) == ["Plain", "Joined together {name}"]


def test_files():
    ## Two per language, like messages.po and themes.po were.
    names = {path.name for path in LOCALES_DIR.glob("*.json")}
    assert {"strings.json", "strings.themes.json", "de_DE.json", "de_DE.themes.json"} <= names
    assert "en_US" in LANGUAGES and len(LANGUAGES) >= 15
    for lang in LANGUAGES:
        assert {f"{lang}.json", f"{lang}.themes.json"} <= names


@pytest.mark.parametrize("lang", LANGUAGES)
def test_language_file(lang):
    strings = i18n_tool.read_strings()
    for domain in i18n.DOMAINS:
        translations = json.loads(i18n.language_file(LOCALES_DIR, lang, domain).read_text(encoding="utf-8"))
        assert isinstance(translations, dict)
        for source, translation in translations.items():
            assert source in strings[domain], f"{domain}: not used any more: {source!r}"
            assert isinstance(translation, str) and translation
            ## A lost {placeholder} shows the wrong text (line breaks are the translator's call).
            assert not [problem for problem in i18n_tool.problems(source, translation) if "line breaks" not in problem], source


def test_problems():
    assert i18n_tool.problems("Install {name}", "{name} installieren") == []
    assert i18n_tool.problems("Install {name}", "Installieren") == ["missing {name}"]
    assert i18n_tool.problems("A\nB", "A B") == ["1 line breaks in English, 0 here"]


@pytest.fixture
def restore_language():
    yield
    i18n.load_language(LOCALES_DIR, "en_US")
    i18n.set_theme_translations({})


def test_load_language(tmp_path, restore_language):
    (tmp_path / "xx_XX.json").write_text(json.dumps({"Hello": "Hallo", "Empty": ""}))
    (tmp_path / "xx_XX.themes.json").write_text(json.dumps({"Genres: {port_info.genres}": "Genres: {port_info.genres}!"}))

    i18n.load_language(tmp_path, "xx_XX")
    assert (i18n._("Hello"), i18n._("Empty"), i18n._("Unknown")) == ("Hallo", "Empty", "Unknown")
    assert i18n.theme_text("Genres: {port_info.genres}") == "Genres: {port_info.genres}!"

    ## A theme's own translations come first, for the current language only.
    i18n.set_theme_translations({"xx_XX": {"Genres: {port_info.genres}": "Mine"}, "yy_YY": {"Hello": "No"}})
    assert i18n.theme_text("Genres: {port_info.genres}") == "Mine"
    i18n.set_theme_translations({})
    assert i18n.theme_text("Genres: {port_info.genres}") == "Genres: {port_info.genres}!"

    ## A missing or broken file is English.
    (tmp_path / "zz_ZZ.json").write_text("{ not json")
    for lang in ("zz_ZZ", "nope"):
        i18n.load_language(tmp_path, lang)
        assert i18n._("Hello") == "Hello"


def test_every_language_loads(restore_language):
    import pugwash.lang
    languages = pugwash.lang.lang_list()
    assert {"en_US", "de_DE", "ja_JP"} <= set(languages)
    for lang in languages:
        assert pugwash.lang.check_lang(lang) == lang
    assert pugwash.lang.check_lang("de_DE.UTF-8") == "de_DE"
    assert pugwash.lang.check_lang("de") == "de_DE"
    assert pugwash.lang.check_lang("xx_XX") is None

    i18n.load_language(LOCALES_DIR, "de_DE")
    assert i18n._("Options") != "Options"


SAFETY_CASES = [
    ("{lang_name} (Selected)", "{lang_name} (Ausgewählt)", True),
    ("{lang_name} (Selected)", "(Ausgewählt)", True),
    ("{lang_name} (Selected)", "{bogus} (Ausgewählt)", False),
    ("{lang_name} (Selected)", "{lang_name (Ausgewählt)", False),
    ("{lang_name} (Selected)", "lang_name} (Ausgewählt)", False),
    ("{lang_name} (Selected)", "{{lang_name}} literal", True),
    ("{lang_name} (Selected)", "{0}", False),
    ("Installing {port_name}", "{port_name} wird installiert", True),
    ("Installing {port_name}", "{port_name.title} wird installiert", True),
    ("Installing {port_name}", "{port_name!r:>10}", True),
    ("Options", "Optionen {", False),
    ("Options", "Optionen {x}", False),
    ("Options", "Optionen", True),
    ("Not {a format", "anything {goes", True),
    ]


@pytest.mark.parametrize("text, translation, safe", SAFETY_CASES)
def test_safe_translation(text, translation, safe):
    ## The same answer from PortMaster and from the translation editor's own copy.
    assert i18n.safe_translation(text, translation) is safe
    assert i18n_tool.safe_translation(text, translation) is safe


def test_unsafe_translations_are_english(tmp_path, restore_language):
    ## Would raise in the code's .format() and stop PortMaster: shown in English instead.
    (tmp_path / "xx_XX.json").write_text(json.dumps({
        "{lang_name} (Selected)": "{bogus} (Ausgewählt)",
        "Installing {port_name}": "{port_name} wird installiert",
        "Options": "Optionen {",
        }))

    i18n.load_language(tmp_path, "xx_XX")

    assert i18n._("{lang_name} (Selected)").format(lang_name="Deutsch") == "Deutsch (Selected)"
    assert i18n._("Installing {port_name}").format(port_name="2048") == "2048 wird installiert"
    assert i18n._("Options") == "Options"


def test_every_shipped_translation_formats(restore_language):
    ## Each language's translations are safe to .format() as the English is.
    for lang in LANGUAGES:
        translations = i18n_tool.read_translations(lang)['messages']
        bad = [text for text, translation in translations.items() if translation and not i18n.safe_translation(text, translation)]
        assert bad == [], f"{lang}: {bad}"
