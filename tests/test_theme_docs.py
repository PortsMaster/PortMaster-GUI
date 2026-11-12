# SPDX-License-Identifier: MIT
#
# THEME.md, the theme reference, keeps up with the theme engine: every region key, screen,
# tag and "#" section PortMaster knows (as the theme editor reads them from its code) is in
# it, and every picture it shows is there. A new key fails here until it's documented.

import re

import pytest

from conftest import PM_DIR

from theme_server import schema


ROOT = PM_DIR.parent
DOC = (ROOT / "THEME.md").read_text(encoding="utf-8")

## Screens nobody themes: PortMaster's built-in ones and the one nothing opens.
NOT_THEMED = {"disclaimer", "blank"}


def mentioned(name):
    return f"`{name}`" in DOC or f"`{{{name}}}`" in DOC


@pytest.mark.parametrize("key", sorted(schema.region_keys()))
def test_every_region_key_is_documented(key):
    assert mentioned(key), f"THEME.md doesn't describe the region key {key!r}: add it to Region keys"


@pytest.mark.parametrize("section", sorted(set(schema.sections()) - NOT_THEMED))
def test_every_screen_is_documented(section):
    assert mentioned(section), f"THEME.md doesn't describe the section {section!r}: add it to The screens"


@pytest.mark.parametrize("tag", sorted(schema.template_tags()))
def test_every_tag_is_documented(tag):
    assert mentioned(tag), f"THEME.md doesn't describe the tag {{{tag}}}: add it to Tags"


@pytest.mark.parametrize("key", sorted(schema.TOP_KEYS))
def test_every_top_level_key_is_documented(key):
    assert mentioned(key)


@pytest.mark.parametrize("key", sorted(schema.INFO_KEYS))
def test_every_info_key_is_documented(key):
    assert mentioned(key)


def test_pictures_are_there():
    pictures = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", DOC)
    assert pictures
    missing = [picture for picture in pictures if not (ROOT / picture).is_file()]
    assert not missing, f"THEME.md shows pictures that aren't there (tools/theme_docs.py makes them): {missing}"


def test_links_inside_the_page_go_somewhere():
    ## GitHub's anchors: lower case, spaces as -, no punctuation but - and _.
    anchors = set()
    for heading in re.findall(r"^#+ (.+)$", DOC, re.M):
        anchors.add(re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-"))
    broken = [link for link in re.findall(r"\]\(#([^)]+)\)", DOC) if link not in anchors]
    assert not broken, f"links to headings THEME.md doesn't have: {broken}"
