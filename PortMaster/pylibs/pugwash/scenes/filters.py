# SPDX-License-Identifier: MIT
#
# The ports list filters / sorting screen.

import harbourmaster
from loguru import logger
from gettext import gettext as _
from .base import BaseScene


class FiltersScene(BaseScene):
    def __init__(self, gui, list_scene):
        super().__init__(gui)
        self.scene_title = _("Filters Scene")

        self.load_regions("filter_list", [
            'filter_list',
            ])

        self.list_scene = list_scene
        self.locked_genres = list(list_scene.options['base_filters'])
        self.selected_genres = list(list_scene.options['filters'])
        self.sort_by = list_scene.options.get('sort_by', "alphabetical")
        self.selected_port = list_scene.selected_port()

        if len(list_scene.all_ports) > 0:
            self.selected_port_title = list_scene.all_ports[self.selected_port]['attr']['title']
        else:
            ## Christian_Hatian wins again!
            self.selected_port_title = "2048.zip"

        self.port_list = []

        self.ready = False
        self.update_filters()

    def update_filters(self):
        if self.gui.hm is None:
            return

        filter_translation = {
            # Sorting.
            "alphabetical":     _("Alphabetical"),
            "recently_added":   _("Recently Added"),
            "recently_updated": _("Recently Updated"),
            "total_downloads":  _("Total Downloads"),

            # Genres.
            "action":           _("Action"),
            "adventure":        _("Adventure"),
            "arcade":           _("Arcade"),
            "casino/card":      _("Casino/Card"),
            "fps":              _("First Person Shooter"),
            "platformer":       _("Platformer"),
            "puzzle":           _("Puzzle"),
            "racing":           _("Racing"),
            "rhythm":           _("Rhythm"),
            "rpg":              _("Role Playing Game"),
            "simulation":       _("Simulation"),
            "sports":           _("Sports"),
            "strategy":         _("Strategy"),
            "visual novel":     _("Visual Novel"),
            "other":            _("Other"),

            # Attrs.
            "rtr":              _("Ready to Run"),
            "!rtr":             _("Files Required"),
            "exp":              _("Experimental"),
            "not installed":    _("Not Installed"),
            "update available": _("Update Available"),
            "broken":           _("Broken Ports"),

            # Availability.
            "full":             _("Free game, all files included."),
            "demo":             _("Demo files included."),
            "free":             _("Free external assets needed."),
            "paid":             _("Paid external assets needed."),

            # Runtimes.
            "godot":            _("{runtime_name} Runtime").format(runtime_name="Godot/FRT"),
            "mono":             _("{runtime_name} Runtime").format(runtime_name="Mono"),
            "rlvm":             _("{runtime_name} Runtime").format(runtime_name="RLVM"),
            "jre":              _("{runtime_name} Runtime").format(runtime_name="Java"),
            "solarus":          _("{runtime_name} Runtime").format(runtime_name="Solarus"),
            "weston":           _("{runtime_name} Runtime").format(runtime_name="Weston"),
            "mesa":             _("{runtime_name} Runtime").format(runtime_name="Mesa"),

            # Architecture
            "armhf":            _("ARM 32bit"),
            "aarch64":          _("ARM 64bit"),
            "x86_64":           _("x86 64bit"),
            }

        # Hack to make other appear last, by default the order will be 0, you can set it to -1 for it to appear at the top.
        sort_order = {
            'other': 1,
            }

        genres = self.locked_genres + self.selected_genres
        total_ports = len(self.gui.hm.list_ports_names_new(genres))

        self.tags['filter_list'].bar_select_mode = 'full'

        first_add = True
        add_blank = False

        selected_option = self.tags['filter_list'].selected_option()
        selected_offset = 0

        self.tags['filter_list'].reset_options()

        DISPLAY_ORDER = [
            'sort',
            'clear-filters',
            'attr',
            # 'status',
            'genres',
            # 'architecture',
            'porters',
            ]

        for display_order in DISPLAY_ORDER:
            first_add = True

            if display_order == 'sort':
                for hm_sort_order in harbourmaster.HM_SORT_ORDER:
                    if hm_sort_order == self.sort_by:
                        text = ["    ", "_CHECKED", f"  {filter_translation.get(hm_sort_order, hm_sort_order)}", None, _("Ascending") + " "]
                    elif (hm_sort_order + '_rev') == self.sort_by:
                        text = ["    ", "_CHECKED", f"  {filter_translation.get(hm_sort_order, hm_sort_order)}", None, _("Descending") + " "]
                    else:
                        text = ["    ", "_UNCHECKED", f"  {filter_translation.get(hm_sort_order, hm_sort_order)}", None, "    "]

                    if first_add:
                        if add_blank:
                            self.tags['filter_list'].add_option(None, "")

                        self.tags['filter_list'].add_option(None, _("Sort:"))
                        first_add = False
                        add_blank = True

                    self.tags['filter_list'].add_option(hm_sort_order, text)

                    if selected_option == hm_sort_order:
                        selected_offset = len(self.tags['filter_list'].options) - 1

            elif display_order == 'clear-filters':
                if len(self.selected_genres) > 0:
                    if add_blank:
                        self.tags['filter_list'].add_option(None, "")

                    add_blank = True
                    self.tags['filter_list'].add_option('clear-filters', ["     ", _("Clear Filters"), "    "])

            elif display_order == 'genres':
                for hm_genre in sorted(harbourmaster.HM_GENRES, key=lambda genre: (sort_order.get(genre, 0), filter_translation.get(genre, genre))):
                    if hm_genre in self.locked_genres:
                        continue

                    if hm_genre in self.list_scene.options['skip_genres']:
                        continue

                    if hm_genre in genres:
                        ports = total_ports
                        text = ["    ", "_CHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports} "]
                    else:
                        ports = len(self.gui.hm.list_ports_names_new(genres + [hm_genre]))
                        text = ["    ", "_UNCHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports} "]

                    if ports == 0:
                        continue

                    if first_add:
                        if add_blank:
                            self.tags['filter_list'].add_option(None, "")

                        self.tags['filter_list'].add_option(None, _("Genres:"))
                        first_add = False
                        add_blank = True

                    self.tags['filter_list'].add_option(hm_genre, text)

                    if selected_option == hm_genre:
                        selected_offset = len(self.tags['filter_list'].options) - 1

            elif display_order == 'attr':
                for hm_genre in ['rtr', '!rtr', 'mono', 'godot', 'solarus', 'rlvm', 'exp', 'not installed', 'update available', 'broken']:
                    if hm_genre in self.locked_genres:
                        continue

                    if hm_genre in self.list_scene.options['skip_genres']:
                        continue

                    if hm_genre in genres:
                        ports = total_ports
                        text = ["    ", "_CHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports}"]
                    else:
                        ports = len(self.gui.hm.list_ports_names_new(genres + [hm_genre]))
                        text = ["    ", "_UNCHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports}"]

                    if ports == 0:
                        continue

                    if first_add:
                        if add_blank:
                            self.tags['filter_list'].add_option(None, "")
                        self.tags['filter_list'].add_option(None, _("Attributes:"))
                        first_add = False

                    self.tags['filter_list'].add_option(hm_genre, text)

                    if selected_option == hm_genre:
                        selected_offset = len(self.tags['filter_list'].options) - 1

            elif display_order == 'architecture':
                for hm_genre in ['armhf', 'aarch64', 'x86_64']:
                    if hm_genre in self.locked_genres:
                        continue

                    if hm_genre in self.list_scene.options['skip_genres']:
                        continue

                    if hm_genre in genres:
                        ports = total_ports
                        text = ["    ", "_CHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports}"]
                    else:
                        ports = len(self.gui.hm.list_ports_names_new(genres + [hm_genre]))
                        text = ["    ", "_UNCHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports}"]

                    if ports == 0:
                        continue

                    if first_add:
                        if add_blank:
                            self.tags['filter_list'].add_option(None, "")
                        self.tags['filter_list'].add_option(None, _("Architecture:"))
                        first_add = False

                    self.tags['filter_list'].add_option(hm_genre, text)

                    if selected_option == hm_genre:
                        selected_offset = len(self.tags['filter_list'].options) - 1

            elif display_order == 'status':
                for hm_genre in ['full', 'demo', 'free', 'paid']:
                    if hm_genre in self.locked_genres:
                        continue

                    if hm_genre in self.list_scene.options['skip_genres']:
                        continue

                    if hm_genre in genres:
                        ports = total_ports
                        text = ["    ", "_CHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports}"]
                    else:
                        ports = len(self.gui.hm.list_ports_names_new(genres + [hm_genre]))
                        text = ["    ", "_UNCHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports}"]

                    if ports == 0:
                        continue

                    if first_add:
                        if add_blank:
                            self.tags['filter_list'].add_option(None, "")
                        self.tags['filter_list'].add_option(None, _("Availability:"))
                        first_add = False

                    self.tags['filter_list'].add_option(hm_genre, text)

                    if selected_option == hm_genre:
                        selected_offset = len(self.tags['filter_list'].options) - 1

            elif display_order == 'porters':
                for hm_genre in sorted(self.gui.hm.porters_list(), key=lambda name: name.lower()):
                    if hm_genre in self.locked_genres:
                        continue

                    if hm_genre in self.list_scene.options['skip_genres']:
                        continue

                    if hm_genre in genres:
                        ports = total_ports
                        text = ["    ", "_CHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports}"]
                    else:
                        ports = len(self.gui.hm.list_ports_names_new(genres + [hm_genre]))
                        text = ["    ", "_UNCHECKED", f"  {filter_translation.get(hm_genre, hm_genre)}", None, "    ", f"  {ports}"]

                    if ports == 0:
                        continue

                    if first_add:
                        if add_blank:
                            self.tags['filter_list'].add_option(None, "")
                        self.tags['filter_list'].add_option(None, _("Porters:"))
                        first_add = False

                    self.tags['filter_list'].add_option(hm_genre, text)

                    if selected_option == hm_genre:
                        selected_offset = len(self.tags['filter_list'].options) - 1

        self.tags['filter_list'].list_select(selected_offset, direction=1)

        self.ready = True

    def do_update(self, events):
        super().do_update(events)
        if not self.ready:
            self.update_filters()
            if not self.ready:
                return True

        if events.was_pressed('A'):
            selected_filter = self.tags['filter_list'].options[self.tags['filter_list'].selected]
            if selected_filter is None:
                return True

            if selected_filter in harbourmaster.HM_SORT_ORDER:
                if self.sort_by == selected_filter:
                    selected_filter += '_rev'

                logger.debug(f"{self.sort_by} -> {selected_filter}")
                self.sort_by = selected_filter
                self.list_scene.options['sort_by'] = selected_filter
                self.list_scene.update_ports()
                self.list_scene.tags['ports_list'].list_select(0)
                self.update_filters()
                self.button_activate()
                return True

            if selected_filter == 'clear-filters':
                self.selected_genres.clear()

            elif selected_filter in self.selected_genres:
                self.selected_genres.remove(selected_filter)

            else:
                self.selected_genres.append(selected_filter)

            self.update_filters()
            self.list_scene.options['filters'] = self.selected_genres
            self.list_scene.update_ports()
            self.list_scene.try_to_select(self.selected_port, self.selected_port_title)
            self.button_activate()
            return True

        if events.was_pressed('B') or events.was_pressed('X'):
            self.button_back()
            self.gui.pop_scene()
            return True

        return True
