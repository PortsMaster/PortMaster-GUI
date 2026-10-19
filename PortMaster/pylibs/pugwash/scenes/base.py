# SPDX-License-Identifier: MIT
#
# StringFormatter (the {tag} template text) and BaseScene, which loads a theme section into regions.

import functools
import json
from harbourmaster.i18n import theme_text
from pugwash import sdl
from loguru import logger


def plain_font():
    """
    PortMaster's own font for the language (the default theme's "font[ja_JP]" & co), for the
    sections a theme doesn't have, where the text has to be readable whatever the theme.
    """
    from pugwash import PYLIB_PATH, lang

    font = "DejaVuSans.ttf"
    try:
        with open(str(PYLIB_PATH / "default_theme" / "theme.json"), encoding="utf-8") as fh:
            base = json.load(fh).get("#base", {})
        font = base.get(f"font[{lang.CURRENT_LANG}]") or base.get("font") or font
    except (OSError, ValueError, AttributeError):
        pass

    return font


class StringFormatter:
    def __init__(self, data_dict):
        self.data_dict = data_dict

    @functools.lru_cache(1024)
    def parse_text(self, text):
        result = []
        current = ''
        while len(text) > 0:
            before, bracket, text = text.partition('{')
            current += before

            if bracket == '' or text == '':
                break

            elif text.startswith('{'):
                current += '{'
                text = text[1:]
                continue

            else:
                token, bracket, text = text.partition('}')
                if bracket == '':
                    current += token
                    break

                if token == '':
                    current += '{}'
                    continue

                result.append((current, token))
                current = ''

        if current != '':
            result.append((current, None))

        return tuple(result)

    def execute_if(self, text, keys_used=None):
        do_not = False

        if text.startswith('!'):
            do_not = True
            text = text[1:]

        if ':' in text:
            key, value = text.split(':', 1)

            if keys_used is not None and key not in keys_used:
                keys_used.append(key)

            if value.startswith(':'):
                value = value[1:]
                if keys_used is not None and value not in keys_used:
                    keys_used.append(value)

                value = self.data_dict.get(value, '')

            result = self.data_dict.get(key, '') == value
        else:
            if keys_used is not None and text not in keys_used:
                keys_used.append(text)

            result = self.data_dict.get(text, '') not in ('', 'None')

        if do_not:
            result = not result

        return result

    def format_string(self, text, keys_used=None):
        output = []
        stack = [True]

        # TRANSLATIONS :D
        text = theme_text(text)

        for before, key in self.parse_text(text):
            if stack[-1] and before != '':
                output.append(before)

            if key is not None:
                if key == 'else':
                    stack[-1] = not stack[-1]

                elif key == 'endif':
                    if len(stack) > 1:
                        stack.pop(-1)

                elif key.startswith('if:'):
                    if_key = key[3:]

                    if self.execute_if(if_key, keys_used):
                        stack.append(True)
                    else:
                        stack.append(False)

                else:
                    if keys_used is not None and key not in keys_used:
                        keys_used.append(key)

                    value = self.data_dict.get(key, f'{{{key}}}')
                    if stack[-1]:
                        output.append(value)

        return ''.join(output)


class BaseScene:
    """
    Scenes handle drawing / logic, different scenes can be transitioned to and or layered.

    Only the top layer receives events.
    """

    def __init__(self, gui):
        self.gui = gui
        self.tags = {}
        self.config = {}
        self.regions = []
        self.text_regions = {}
        self.bar_regions = {}
        self.image_regions = {}
        self.update_regions = {}
        self.music = None
        self.music_volume = 128
        self.active = False
        self.scene_title = ""
        self.scene_tooltip = ""

    def scene_deactivate(self):
        if self.active:
            self.active = False
            self.scene_deactivated()

    def scene_activate(self):
        if not self.active:
            self.gui.animations.change_scene()
            self.active = True
            self.gui.sounds.easy_music(self.music, volume=max(0, min(self.music_volume, 128)))
            self.gui.set_data("scene.title", self.scene_title)
            self.gui.set_data("scene.tooltip", self.scene_tooltip)
            self.scene_activated()

    def scene_deactivated(self):
        ...

    def scene_activated(self):
        ...

    def set_tooltip(self, text):
        self.scene_tooltip = text
        self.gui.set_data("scene.tooltip", text)

    def load_regions(self, section, required_tags):
        rects = self.gui.new_rects()
        temp_required_tags = list(required_tags)

        for number, (region_name, region_data) in enumerate(self.gui.theme_data[section].items()):
            if region_name == "#config":
                self.config = region_data
                continue

            if "music" in region_data:
                self.music = region_data["music"]
                self.music_volume = region_data.get("music-volume", 128)

            # print(f"Loading region {region_name}: {region_data}")
            region = sdl.Region(self.gui, region_data, region_name, number, rects)

            if "image" in region_data and "{" in region_data["image"]:
                image_keys = []
                region.image = self.gui.images.load(self.gui.format_data(region_data["image"], image_keys))

                self.image_regions[region_name] = (region, region_data["image"])
                for key in image_keys:
                    self.update_regions.setdefault(key, []).append(region_name)

            if "text" in region_data and "{" in region_data["text"]:
                text_keys = []
                region.text = self.gui.format_data(region_data["text"], text_keys)

                self.text_regions[region_name] = (region, region_data["text"])
                for key in text_keys:
                    self.update_regions.setdefault(key, []).append(region_name)

            if "bar" in region_data:
                ## Fill in the {templates} for the region, the theme's own list stays as it is
                ## so the next scene made from it (eg: the next messages window) has them too.
                found = False
                text_keys = []
                bar_copy = region_data["bar"][:]
                new_bar = bar_copy[:]
                for i, bar_item in enumerate(bar_copy):
                    if not isinstance(bar_item, str) or "{" not in bar_item:
                        continue

                    found = True
                    new_bar[i] = self.gui.format_data(bar_item, text_keys)

                if found:
                    region.bar = new_bar
                    self.bar_regions[region_name] = (region, bar_copy)
                    for key in text_keys:
                        self.update_regions.setdefault(key, []).append(region_name)

            region_tag = region_data.get("tag", region_name)
            if region_tag is not None:
                self.tags[region_tag] = region

            if region_tag in temp_required_tags:
                temp_required_tags.remove(region_tag)

            self.regions.append(region)

        if len(temp_required_tags) > 0:
            logger.error(f"Error: missing one or more tags for section {section}: {', '.join(temp_required_tags)}")
            raise RuntimeError("Error missing section tag in theme")

        self.regions.sort(key=lambda x: (x.z_index, x.z_position))

        if "buttons" in self.config:
            if "A" in self.config["buttons"]:
                del self.config["buttons"]["A"]

            if "B" in self.config["buttons"]:
                del self.config["buttons"]["B"]

            if "X" in self.config["buttons"]:
                del self.config["buttons"]["X"]

            if "Y" in self.config["buttons"]:
                del self.config["buttons"]["Y"]

    def update_data(self, keys):
        regions = set()

        for key in keys:
            if key in self.update_regions:
                regions.update(self.update_regions[key])

        for region_name in regions:
            if region_name in self.image_regions:
                region, text = self.image_regions[region_name]
                new_image = self.gui.format_data(text)
                # print(f"Loading image {region} -> {text} -> {new_image}")
                region.image = self.gui.images.load(new_image)
                self.gui.updated = True

            if region_name in self.text_regions:
                region, text = self.text_regions[region_name]
                region.text = self.gui.format_data(text)
                self.gui.updated = True

            elif region_name in self.bar_regions:
                region, bar = self.bar_regions[region_name]
                new_bar = bar[:]

                for i, bar_item in enumerate(bar):                    
                    if not isinstance(bar_item, str) or "{" not in bar_item:
                        continue

                    new_bar[i] = self.gui.format_data(bar_item)

                region.bar = new_bar
                self.gui.updated = True

    def do_update(self, events):
        for region in self.regions:
            # print(f"DRAW {region}")
            region.update()

        return False

    def do_draw(self):
        for region in self.regions:
            # print(f"DRAW {region}")
            if not region.visible:
                continue

            region.draw()

    def set_buttons(self, key_map):
        key_to_image = {
            'A':     '_A',
            'B':     '_B',
            'X':     '_X',
            'Y':     '_Y',
            'UP':    '_UP',
            'DOWN':  '_DOWN',
            'LEFT':  '_LEFT',
            'RIGHT': '_RIGHT',
            'START': '_START',
            'SELECT': '_SELECT',
            'L': '_L',
            'R': '_R',
            }

        if 'button_bar' not in self.tags:
            return

        if len(key_map) == 0:
            self.tags['button_bar'].bar = None
            return

        if self.gui.SWAP_BUTTONS:
            key_to_image['A'], key_to_image['B'] = key_to_image['B'], key_to_image['A']
            key_to_image['X'], key_to_image['Y'] = key_to_image['Y'], key_to_image['X']

        actions = {}

        for key, action in key_map.items():
            actions.setdefault(action, []).append(key_to_image.get(key, key))

        output = []
        for action, key in actions.items():
            output.extend(key)
            output.append(action)

        # print(f"-> {key_map} = {output}")

        self.tags['button_bar'].bar = output

    def button_activate(self):
        if 'button_bar' not in self.tags:
            return

        self.gui.sounds.play(self.tags['button_bar'].button_sound, volume=self.tags['button_bar'].button_sound_volume)

    def button_back(self):
        if 'button_bar' not in self.tags:
            return

        if self.tags['button_bar'].button_sound_alt is None:
            self.button_activate()

        else:
            self.gui.sounds.play(self.tags['button_bar'].button_sound_alt, volume=self.tags['button_bar'].button_sound_alt_volume)

    def config_buttons(self, events):
        if "buttons" not in self.config:
            return

        for button, action in self.config.get("buttons", {}).items():
            if events.was_pressed(button):
                yield action


class BlankScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)

        self.load_regions("blank", [])
        self.set_buttons({})
