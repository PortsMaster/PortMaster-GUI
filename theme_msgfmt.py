#!/usr/bin/env python3
#
# SPDX-License-Identifier: MIT
#

"""

This is used to create the themes.json and themes.pot file on PR.

"""

import datetime
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib
import urllib.request

from pathlib import Path


THEME_TRANSLATIONS = "https://github.com/PortsMaster/PortMaster-Themes/releases/latest/download/theme_translations.json"
TRANSLATION_HEADER = r"""# SOME DESCRIPTIVE TITLE.
# Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER
# This file is distributed under the same license as the PACKAGE package.
# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.
#
msgid ""
msgstr ""
"Project-Id-Version: PACKAGE VERSION\n"
"Report-Msgid-Bugs-To: \n"
"POT-Creation-Date: 2023-09-09 16:35+0800\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: LANGUAGE <LL@li.org>\n"
"Language: \n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"

"""


def fetch_url(url):
    try:
        # Open the URL
        with urllib.request.urlopen(url) as response:
            # Read the content of the file
            file_content = response.read()

        # Decode the bytes to a string (assuming the file is in UTF-8 encoding)
        return file_content.decode('utf-8')

    except urllib.error.URLError as e:
        return None

    except UnicodeDecodeError as e:
        return None


def parse_translations(theme_name, translations, text):
    source_name = f"{theme_name}/theme.json"

    for lineno, line in enumerate(text.split('\n'), 1):
        line_1=line.strip()
        if not line_1.startswith('"text":'):
            continue

        line_2 = line_1.split('"', 3)[-1]
        line_3 = line_2.rsplit('"', 1)[0]

        if line_3.strip() == "":
            continue

        if re.match(r"^\{[^}]+\}$", line_3):
            continue

        if re.match(r"^#[0-9a-f]+$", line_3, re.I):
            continue

        source = f"{source_name}:{lineno}"
        translations.setdefault(line_3, []).append(source)


def dump_tr_string(string):
    if "\\n" in string:
        result = ['""']
        items = string.split("\\n")
        for line in items[:-1]:
            result.append(f'"{line}\\n"')
        result.append(f'"{items[-1]}"')
        return "\n".join(result)

    return f'"{string}"'


def dump_translations(file_name, translations):
    with open(file_name, "w") as fh:
        print(TRANSLATION_HEADER, file=fh)

        for translation, sources in translations.items():
            for offset in range(0, len(sources), 5):
                print(f"#: {', '.join(sources[offset:(offset+5)])}", file=fh)

            print(f"msgid {dump_tr_string(translation)}", file=fh)
            print(f"msgstr {dump_tr_string('')}", file=fh)
            print("", file=fh)


def main():
    theme_paths = Path('PortMaster/pylibs/')

    theme_translations = fetch_url(THEME_TRANSLATIONS)

    if theme_translations is not None:
        translations = json.loads(theme_translations)
    else:
        translations = {}

    for theme_file in theme_paths.glob("*/theme.json"):
        parse_translations(theme_file.parent.name, translations, theme_file.read_text())

    dump_translations("PortMaster/pylibs/locales/themes.pot", translations)


if __name__ == '__main__':
    main()
