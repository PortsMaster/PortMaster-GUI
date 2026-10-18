#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# PortMaster's translatable strings (see harbourmaster/i18n.py for the files).
#
#   python3 -I tools/i18n.py extract [--themes DIR]
#       Rewrites PortMaster/pylibs/locales/strings.json, every _("...") in the code, and
#       strings.themes.json, every theme "text" in the built-in theme (and the themes in
#       DIR, eg: a PortMaster-Themes checkout; themes it doesn't scan keep their strings).
#   python3 -I tools/i18n.py check
#       Each language file: strings that aren't in strings.json any more, and translations
#       that lost a {placeholder} or a line break.
#
# Standard library only, Python 3.7.

import argparse
import ast
import json
import re
import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent.parent
PM_DIR = REPO_DIR / "PortMaster"
LOCALES_DIR = PM_DIR / "pylibs" / "locales"
DOMAINS = ("messages", "themes")
## The files: strings.json, de_DE.json (messages); strings.themes.json, de_DE.themes.json (themes).
LANGUAGE_FILE = re.compile(r"^([a-z]{2,3}_[A-Z]{2})(\.themes)?\.json$")


def domain_file(name, domain):
    return LOCALES_DIR / (f"{name}.json" if domain == "messages" else f"{name}.{domain}.json")


def languages():
    """The languages with a translation file."""
    return sorted({LANGUAGE_FILE.match(path.name).group(1) for path in LOCALES_DIR.glob("*.json") if LANGUAGE_FILE.match(path.name)})


def code_files():
    """The files with translatable strings: both scripts' own code and the two packages."""
    files = [PM_DIR / "pugwash", PM_DIR / "harbourmaster"]
    for package in ("harbourmaster", "pugwash"):
        files += sorted((PM_DIR / "pylibs" / package).rglob("*.py"))
    return files


def _literal(node):
    """The string of a str literal node, None for anything else (f-strings, names, ...)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, getattr(ast, "Str", ())) and isinstance(getattr(node, "s", None), str):
        return node.s
    return None


def _display(path):
    """A file as strings.json names it: relative to PortMaster/ when it's in there."""
    try:
        return Path(path).resolve().relative_to(PM_DIR).as_posix()
    except ValueError:
        return Path(path).as_posix()


def code_strings(files=None):
    """{text: ["file:line", ...]} for every _("text") call, in file order."""
    found = {}
    for path in files or code_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_" and node.args]
        for node in sorted(calls, key=lambda node: (node.lineno, node.col_offset)):
            text = _literal(node.args[0])
            if text:
                found.setdefault(text, []).append(f"{_display(path)}:{node.lineno}")

    return found


def theme_strings(theme_dir, name=None):
    """{text: ["theme/theme.json:line", ...]} for a theme's "text" values that are more
    than a {template} or a colour."""
    theme_file = Path(theme_dir) / "theme.json"
    source = theme_file.read_text(encoding="utf-8")
    name = name or Path(theme_dir).name
    found = {}

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.split("[", 1)[0] == "text" and isinstance(item, str):
                    yield item
                else:
                    yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    lines = source.split("\n")
    for text in walk(json.loads(source)):
        if not text.strip() or re.match(r"^\{[^}]+\}$", text) or re.match(r"^#[0-9a-f]+$", text, re.I):
            continue
        quoted = json.dumps(text, ensure_ascii=False)[1:-1]
        line = next((number for number, line in enumerate(lines, 1) if quoted in line), 0)
        found.setdefault(text, []).append(f"{name}/theme.json:{line}")

    return found


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_strings():
    """{domain: {text: [where it's used]}}"""
    return {domain: read_json(domain_file("strings", domain)) for domain in DOMAINS}


def read_translations(lang):
    """{domain: {text: translation}}"""
    return {domain: read_json(domain_file(lang, domain)) for domain in DOMAINS}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def extract(themes_dirs=()):
    strings = read_strings()
    themes = {"default_theme": PM_DIR / "pylibs" / "default_theme"}
    for themes_dir in themes_dirs:
        for theme_file in sorted(Path(themes_dir).glob("*/theme.json")):
            themes[theme_file.parent.name] = theme_file.parent

    ## Themes not scanned this time keep their strings.
    kept = {}
    for text, sources in strings['themes'].items():
        others = [source for source in sources if source.split("/", 1)[0] not in themes]
        if others:
            kept[text] = others

    for name, theme_dir in themes.items():
        for text, sources in theme_strings(theme_dir, name).items():
            kept.setdefault(text, []).extend(sources)

    return {'messages': code_strings(), 'themes': {text: kept[text] for text in sorted(kept, key=lambda t: (kept[t][0], t))}}


PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def problems(source, translation):
    """What a translation lost: {placeholders} and line breaks the English has."""
    found = []
    missing = sorted(set(PLACEHOLDER.findall(source)) - set(PLACEHOLDER.findall(translation)))
    if missing:
        found.append("missing " + ", ".join(missing))
    extra = sorted(set(PLACEHOLDER.findall(translation)) - set(PLACEHOLDER.findall(source)))
    if extra:
        found.append("unknown " + ", ".join(extra))
    if source.count("\n") != translation.count("\n"):
        found.append(f"{source.count(chr(10))} line breaks in English, {translation.count(chr(10))} here")
    return found


def check():
    strings = read_strings()
    issues = 0
    for lang in languages():
        for domain, translations in read_translations(lang).items():
            name = domain_file(lang, domain).name
            for source, translation in translations.items():
                if source not in strings[domain]:
                    print(f"{name}: not used any more: {source!r}")
                    issues += 1
                for problem in problems(source, translation):
                    print(f"{name}: {problem}: {source!r}")
                    issues += 1

    return 1 if issues else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="PortMaster's translatable strings")
    commands = parser.add_subparsers(dest="command")
    extract_parser = commands.add_parser("extract", help="rewrite locales/strings.json")
    extract_parser.add_argument("--themes", action="append", default=[], help="a folder of themes to scan too")
    commands.add_parser("check", help="check the language files")
    options = parser.parse_args(argv)

    if options.command == "extract":
        strings = extract(options.themes)
        for domain in DOMAINS:
            write_json(domain_file("strings", domain), strings[domain])
        print(f"{len(strings['messages'])} code strings, {len(strings['themes'])} theme strings -> {LOCALES_DIR}")
        return 0

    if options.command == "check":
        return check()

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
