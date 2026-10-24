# SPDX-License-Identifier: MIT
#
# tools/i18n.py (theme_server/translations.py): finding the translatable strings in the code
# and the themes, keeping strings.json up to date, and checking the language files.

import json
import shutil

import pytest

from conftest import PM_DIR

from theme_server import translations as tool


@pytest.fixture
def locales(tmp_path, monkeypatch):
    """A copy of the locales folder the tool works on: the checkout's is never written."""
    locales = tmp_path / "locales"
    shutil.copytree(str(PM_DIR / "pylibs" / "locales"), str(locales))
    monkeypatch.setattr(tool, "LOCALES_DIR", locales)
    return locales


def write_code(path, text):
    path.write_text(text, encoding="utf-8")
    return path


################################################################################
## Finding strings in code
def test_code_strings(tmp_path):
    code = write_code(tmp_path / "a.py", '\n'.join([
        'from harbourmaster.i18n import _',
        'x = _("Hello")',
        'y = _("Hello")',
        'z = _("Port {name}").format(name="x")',
        'w = _(f"no {x}")',            ## f-strings can't be looked up: skipped
        'v = _(name)',                  ## a variable: skipped
        'u = other("Not this")',
        't = i18n._("Not this either")',
        's = _("")',                    ## empty: nothing to translate
        'r = _("Two\\nlines")',
        ]))

    found = tool.code_strings([code])

    assert list(found) == ["Hello", "Port {name}", "Two\nlines"]
    assert [where.rsplit(":", 1)[1] for where in found["Hello"]] == ["2", "3"]


def test_code_strings_in_file_order(tmp_path):
    a = write_code(tmp_path / "a.py", '_("B")\n_("A")\n')
    b = write_code(tmp_path / "b.py", '_("C")\n_("A")\n')

    found = tool.code_strings([a, b])

    assert list(found) == ["B", "A", "C"]
    assert len(found["A"]) == 2


def test_every_code_file_is_scanned():
    files = tool.code_files()
    names = {path.name for path in files}

    assert {"pugwash", "harbourmaster", "options.py", "hm_install.py", "i18n.py"} <= names
    assert all(path.is_file() for path in files)


################################################################################
## Finding strings in themes
def test_theme_strings(tmp_path):
    theme = tmp_path / "my_theme"
    theme.mkdir()
    (theme / "theme.json").write_text(json.dumps({
        "main_menu": {
            "title": {"text": "Welcome"},
            "status": {"text": "{system.battery_level}"},          ## only a tag
            "colour": {"text": "#ff00aa"},                        ## a colour
            "blank": {"text": "   "},
            "info": {"text[640x480]": "Space: {system.free_space}", "text": "Space"},
            "list": {"options": [{"text": "In a list"}]},
            "not_text": {"title": "Not a text key"},
            },
        }, indent=2), encoding="utf-8")

    found = tool.theme_strings(theme)

    assert set(found) == {"Welcome", "Space: {system.free_space}", "Space", "In a list"}
    ## Where: the theme's name and the line.
    assert found["Welcome"][0].startswith("my_theme/theme.json:") and int(found["Welcome"][0].rsplit(":", 1)[1]) > 1


def test_default_theme_strings_are_in_strings_themes_json():
    found = tool.theme_strings(PM_DIR / "pylibs" / "default_theme", "default_theme")
    assert set(found) <= set(tool.read_strings()["themes"])


################################################################################
## extract: strings.json from the code and the themes
def test_extract_keeps_themes_not_scanned(locales, tmp_path):
    strings = tool.read_strings()
    strings["themes"]["Only in an old theme"] = ["old_theme/theme.json:3"]
    tool.write_json(tool.domain_file("strings", "themes"), strings["themes"])

    extracted = tool.extract()

    assert extracted["themes"]["Only in an old theme"] == ["old_theme/theme.json:3"]
    assert extracted["messages"] == tool.code_strings()


def test_extract_rescans_the_themes_it_is_given(locales, tmp_path):
    themes = tmp_path / "themes"
    (themes / "old_theme").mkdir(parents=True)
    (themes / "old_theme" / "theme.json").write_text(json.dumps({"s": {"r": {"text": "New text"}}}))
    strings = tool.read_strings()
    strings["themes"]["Gone from old_theme"] = ["old_theme/theme.json:3"]
    tool.write_json(tool.domain_file("strings", "themes"), strings["themes"])

    extracted = tool.extract([themes])

    assert "Gone from old_theme" not in extracted["themes"]
    assert extracted["themes"]["New text"] == ["old_theme/theme.json:1"]


def test_main_extract_writes_strings_json(locales, capsys):
    (locales / "strings.json").write_text("{}")

    assert tool.main(["extract"]) == 0

    assert json.loads((locales / "strings.json").read_text(encoding="utf-8")) == tool.code_strings()
    assert "code strings" in capsys.readouterr().out


def test_strings_json_is_up_to_date():
    ## tools/i18n.py extract has been run: the checkout's strings.json is the code's.
    assert list(tool.read_strings()["messages"]) == list(tool.code_strings())


################################################################################
## check: the language files
def test_check_is_clean():
    ## Every shipped translation keeps the English's placeholders, line breaks and spaces.
    assert tool.check() == 0


def test_check_reports(locales, capsys):
    de = tool.read_translations("de_DE")["messages"]
    de["Not a string any more"] = "Nicht mehr"
    de["Port {download_name} failed to install."] = "Port konnte nicht installiert werden."
    de["Music: "] = "Musik:"
    tool.write_json(tool.domain_file("de_DE", "messages"), de)

    assert tool.check() == 1

    out = capsys.readouterr().out
    assert "de_DE.json: not used any more: 'Not a string any more'" in out
    assert "missing {download_name}" in out
    assert "English ends with a space" in out


def test_main_check_and_help(locales, capsys):
    assert tool.main(["check"]) == 0
    assert tool.main([]) == 2
    assert "extract" in capsys.readouterr().out


################################################################################
## problems: what a translation lost
@pytest.mark.parametrize("source, translation, expected", [
    ("Hello", "Hallo", []),
    ("Port {name}", "{name} Port", []),
    ("Port {name}", "Port", ["missing {name}"]),
    ("Port", "Port {name}", ["unknown {name}"]),
    ("Port {a} {b}", "{b} {c}", ["missing {a}", "unknown {c}"]),
    ("Music: ", "Musik:", ["English ends with a space, this doesn't"]),
    ("Music: ", "Musik: ", []),
    (" x", "x", ["English starts with a space, this doesn't"]),
    ("\n\nIn order", "Um", ["English starts with a space, this doesn't", "2 line breaks in English, 0 here"]),
    ("A\nB", "A B", ["1 line breaks in English, 0 here"]),
    ("A B", "A\nB", ["0 line breaks in English, 1 here"]),
    ("{if:x}Yes{endif}", "{if:x}Ja{endif}", []),
    ("{if:x}Yes{endif}", "Ja", ["missing {endif}, {if:x}"]),
    ])
def test_problems(source, translation, expected):
    assert tool.problems(source, translation) == expected


################################################################################
## The files
def test_languages(locales):
    (locales / "notalang.json").write_text("{}")
    (locales / "xx_XXX.json").write_text("{}")
    (locales / "qq_QQ.themes.json").write_text("{}")

    langs = tool.languages()

    assert "notalang" not in langs and "xx_XXX" not in langs
    ## A language with only its themes file is still a language.
    assert "qq_QQ" in langs and "de_DE" in langs and "en_US" in langs


def test_domain_files():
    assert tool.domain_file("strings", "messages").name == "strings.json"
    assert tool.domain_file("strings", "themes").name == "strings.themes.json"
    assert tool.domain_file("de_DE", "themes").name == "de_DE.themes.json"


@pytest.mark.parametrize("contents", ["", "[1]", "{ bad", "null"])
def test_read_json_bad(tmp_path, contents):
    (tmp_path / "x.json").write_text(contents)
    assert tool.read_json(tmp_path / "x.json") == {}
    assert tool.read_json(tmp_path / "missing.json") == {}


def test_write_json_keeps_unicode(tmp_path):
    tool.write_json(tmp_path / "x.json", {"Options": "オプション"})
    text = (tmp_path / "x.json").read_text(encoding="utf-8")
    assert "オプション" in text and text.endswith("\n")
