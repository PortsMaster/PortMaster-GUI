# SPDX-License-Identifier: MIT
#
# Checks on our own source code that the linters don't make.

import ast

import pytest

from conftest import PM_DIR


OUR_CODE = sorted(
    list((PM_DIR / "pylibs" / "harbourmaster").rglob("*.py")) +
    list((PM_DIR / "pylibs" / "pugwash").rglob("*.py")) +
    [PM_DIR / "pugwash", PM_DIR / "harbourmaster"])


def _jumps_out_of_finally(tree):
    """`return` / `break` / `continue` in a finally block silently drop the exception
    being raised (a SyntaxWarning from Python 3.14), eg: Ctrl+C mid install."""
    found = []

    def visit(node, in_finally, in_loop):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            in_finally, in_loop = False, False

        if in_finally and isinstance(node, ast.Return):
            found.append(node.lineno)

        if in_finally and not in_loop and isinstance(node, (ast.Break, ast.Continue)):
            found.append(node.lineno)

        if isinstance(node, ast.Try):
            for child in node.body + node.handlers + node.orelse:
                visit(child, in_finally, in_loop)

            for child in node.finalbody:
                visit(child, True, False)

            return

        child_in_loop = in_loop or isinstance(node, (ast.For, ast.While, ast.AsyncFor))
        for child in ast.iter_child_nodes(node):
            visit(child, in_finally, child_in_loop)

    visit(tree, False, False)
    return found


@pytest.mark.parametrize("source", OUR_CODE, ids=lambda path: str(path.relative_to(PM_DIR)))
def test_no_jumps_out_of_finally(source):
    tree = ast.parse(source.read_text(), str(source))
    assert _jumps_out_of_finally(tree) == []


def test_check_finds_them():
    tree = ast.parse(
        "def f():\n"
        "    try:\n"
        "        pass\n"
        "    finally:\n"
        "        return 1\n"
        "for x in y:\n"
        "    try:\n"
        "        pass\n"
        "    finally:\n"
        "        for z in x:\n"
        "            break\n"
        "        continue\n")

    assert _jumps_out_of_finally(tree) == [5, 12]


def test_spruce_marker_does_not_shadow_platform_package():
    ## pylibs/harbourmaster/platform.py only exists for spruce's launch.sh grep.
    import harbourmaster.platform

    marker = PM_DIR / "pylibs" / "harbourmaster" / "platform.py"
    assert "PlatformSpruce" in marker.read_text()
    assert ast.parse(marker.read_text()).body == []

    assert harbourmaster.platform.__file__.endswith("__init__.py")
    assert 'spruce' in harbourmaster.platform.HM_PLATFORMS
