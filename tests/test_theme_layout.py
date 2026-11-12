# SPDX-License-Identifier: MIT
#
# theme_server.layout: what a screen's regions drew, turned into problems. The default
# theme's own check, at many screen sizes, is in test_theme_server.py (it needs renderers).

import json

from theme_server import layout


def region(name, rect, drawn, depth=0, visible=True):
    return {'name': name, 'rect': rect, 'drawn': drawn, 'depth': depth, 'visible': visible}


def kinds(found):
    return sorted(problem['kind'] for problem in found)


def test_side_by_side_is_fine():
    regions = [
        region("list", [0, 0, 300, 480], [['text', 10, 10, 200, 20, 1.0]]),
        region("info", [300, 0, 340, 480], [['text', 310, 10, 300, 60, 1.0], ['image', 310, 80, 300, 200, 1.0]]),
        ]
    assert layout.problems(regions, (640, 480)) == []


def test_clash():
    regions = [
        region("info", [300, 0, 340, 300], [['text', 310, 200, 300, 60, 1.0]]),
        region("desc", [300, 240, 340, 240], [['text', 310, 240, 300, 100, 1.0]]),
        ]
    (problem,) = layout.problems(regions, (640, 480))
    assert problem['kind'] == "clash" and problem['regions'] == ["info", "desc"]
    assert problem['rect'] == [310, 240, 300, 20]
    assert layout.errors([problem]) == [problem]


def test_touching_and_slack_are_fine():
    regions = [
        region("a", [0, 0, 640, 100], [['text', 0, 0, 640, 100, 1.0]]),
        region("b", [0, 97, 640, 100], [['text', 0, 97, 640, 100, 1.0]]),     ## 3 pixels: rounding
        ]
    assert layout.problems(regions, (640, 480)) == []


def test_another_depth_is_a_popup():
    regions = [
        region("list", [0, 0, 640, 480], [['text', 0, 0, 640, 480, 1.0]], depth=0),
        region("message", [100, 100, 440, 280], [['text', 100, 100, 440, 280, 1.0]], depth=1),
        ]
    assert layout.problems(regions, (640, 480)) == []


def test_a_mask_in_the_same_box_is_decoration():
    regions = [
        region("port_image", [300, 40, 300, 225], [['image', 300, 40, 300, 225, 1.0]]),
        region("port_image_corners", [300, 40, 300, 225], [['image', 300, 40, 300, 225, 1.0]]),
        ]
    assert layout.problems(regions, (640, 480)) == []
    ## Text on text in the same box still collides.
    regions = [
        region("progress", [20, 400, 600, 20], [['text', 20, 400, 300, 20, 1.0]]),
        region("amount", [20, 400, 600, 20], [['text', 250, 400, 100, 20, 1.0]]),
        ]
    assert kinds(layout.problems(regions, (640, 480))) == ["clash"]


def test_the_themes_own_art_is_not_content():
    panel = region("panel_back", [0, 0, 640, 480], [['image', 0, 0, 640, 480, 1.0]])
    panel['data'] = {'image': "panel.png"}
    text = region("ports_list", [10, 10, 300, 400], [['text', 10, 10, 200, 20, 1.0]])
    assert layout.problems([panel, text], (640, 480)) == []
    ## A screenshot is content, whatever it is drawn over.
    shot = region("port_image", [100, 0, 300, 200], [['image', 100, 0, 300, 200, 1.0]])
    shot['data'] = {'image': "{port_info.image}"}
    assert kinds(layout.problems([shot, text], (640, 480))) == ["clash"]


def test_a_text_regions_own_panel_and_a_shadow():
    ## A fixed image behind a region's own text is its panel; the same text twice is a shadow.
    info = region("info", [300, 200, 340, 100], [['image', 300, 200, 340, 100, 1.0], ['text', 310, 210, 300, 40, 1.0]])
    info['data'] = {'image': "panel.png", 'text': "{port_info.genres}"}
    desc = region("desc", [300, 280, 340, 100], [['image', 300, 280, 340, 100, 1.0], ['text', 310, 300, 300, 40, 1.0]])
    desc['data'] = {'image': "panel.png", 'text': "{port_info.description}"}
    assert layout.problems([info, desc], (640, 480)) == []
    back = region("title_back", [300, 0, 340, 40], [['text', 400, 5, 120, 30, 1.0]])
    back['data'] = {'text': "{port_info.title}"}
    title = region("title", [300, 0, 340, 40], [['text', 400, 5, 120, 30, 1.0]])
    title['data'] = {'text': "{port_info.title}"}
    assert layout.problems([back, title], (640, 480)) == []


def test_hidden_or_empty_regions_dont_count():
    regions = [
        region("a", [0, 0, 640, 480], [['text', 0, 0, 640, 480, 1.0]]),
        region("hidden", [0, 0, 640, 480], [['text', 0, 0, 640, 480, 1.0]], visible=False),
        region("panel", [0, 0, 640, 480], []),
        ]
    assert layout.problems(regions, (640, 480)) == []


def test_off_screen_and_outside_its_box():
    regions = [region("bar", [0, 440, 600, 30], [['image', -40, 440, 30, 30, 1.0]])]
    assert kinds(layout.problems(regions, (640, 480))) == ["off screen", "outside its box"]


def test_scaled_text_and_pointers_are_warnings():
    regions = [
        region("bar", [0, 440, 600, 30], [['text', 10, 445, 100, 20, 0.8]]),
        region("list", [0, 0, 300, 400], [['pointer', 290, 10, 51, 25, 1.0]]),
        region("info", [320, 0, 320, 400], [['text', 320, 10, 300, 100, 1.0]]),
        ]
    found = layout.problems(regions, (640, 480))
    assert kinds(found) == ["pointer clash", "scaled text"]
    assert layout.errors(found) == []


def test_check_export(tmp_path):
    folder = tmp_path / "Mine" / "640x480" / "Dark" / "en_US"
    folder.mkdir(parents=True)
    (folder / "main_menu.json").write_text(json.dumps({'regions': [region("a", [0, 0, 10, 10], [['text', 0, 0, 10, 10, 1.0]])]}))
    (folder / "options.json").write_text(json.dumps({'regions': [region("a", [0, 0, 10, 10], [['text', 700, 0, 10, 10, 1.0]])]}))
    results = layout.check_export(tmp_path)
    assert results[("Mine", "640x480", "Dark", "en_US", "main_menu")] == []
    assert kinds(results[("Mine", "640x480", "Dark", "en_US", "options")]) == ["off screen", "outside its box"]
    assert layout.main([str(tmp_path)]) == 1


def test_check_export_with_layouts(tmp_path, capsys):
    ## serve.py --layouts: a folder for the layout, so a key has six parts.
    folder = tmp_path / "Mine" / "640x480" / "Dark" / "Grid" / "en_US"
    folder.mkdir(parents=True)
    (folder / "options.json").write_text(json.dumps({'regions': [region("a", [0, 0, 10, 10], [['text', 700, 0, 10, 10, 1.0]])]}))
    results = layout.check_export(tmp_path)
    assert list(results) == [("Mine", "640x480", "Dark", "Grid", "en_US", "options")]
    assert layout.main([str(tmp_path)]) == 1
    assert "Mine 640x480 Dark Grid en_US options:" in capsys.readouterr().out
