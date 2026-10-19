# SPDX-License-Identifier: MIT
#
# PortMasterGUI PortInfoMixin.

import os
import urllib.parse
import harbourmaster
from harbourmaster.i18n import _


## The port's page on the website, for ports from the PortMaster and Multiverse sources.
WEBSITE_PORT_URL = "https://portmaster.games/detail.html?name={name}"

## port.json "store" names are typed by hand: "Itch", "itch.io", "GoG", "Steam ", ...
STORE_NAMES = {
    'steam':        "Steam",
    'itch':         "itch.io",
    'itchio':       "itch.io",
    'gog':          "GOG",
    'gogcom':       "GOG",
    'gamejolt':     "Game Jolt",
    'playstore':    "Google Play",
    'googleplay':   "Google Play",
    'appstore':     "App Store",
    'humble':       "Humble Bundle",
    'humblebundle': "Humble Bundle",
    'github':       "GitHub",
    'dlsite':       "DLsite",
    'epic':         "Epic Games Store",
    'epicgames':    "Epic Games Store",
    'epicgamesstore': "Epic Games Store",
    }


def store_name(name, url):
    key = ''.join(char for char in name.casefold() if char.isalnum())
    if key in STORE_NAMES:
        return STORE_NAMES[key]

    if name.strip() != '':
        return name.strip()

    host = urllib.parse.urlsplit(url).hostname or url
    if host.startswith('www.'):
        host = host[4:]

    return host


def port_links(port_name, port_info, website=False):
    """
    The links for a port, as a list of (label, kind, url): the PortMaster website first (if
    `website`), then each of its stores, the game's page and then the developer's.
    """
    links = []
    seen = set()

    def add(label, kind, url):
        if not isinstance(url, str):
            return

        url = url.strip()
        if not url.casefold().startswith(('http://', 'https://')) or url in seen:
            return

        seen.add(url)
        links.append((label, kind, url))

    if website:
        name = harbourmaster.name_cleaner(port_name)
        if name.endswith('.zip'):
            name = name[:-4]

        add(_("PortMaster website"), 'website', WEBSITE_PORT_URL.format(name=urllib.parse.quote(name, safe='')))

    stores = (port_info or {}).get('attr', {}).get('store', None)
    if not isinstance(stores, list):
        stores = []

    for store in stores:
        if not isinstance(store, dict):
            continue

        game_url = store.get('gameurl') or store.get('url') or ''
        dev_url = store.get('developerurl') or ''
        name = store.get('name') if isinstance(store.get('name'), str) else ''
        label = store_name(name, isinstance(game_url, str) and game_url or str(dev_url))

        add(label, 'store', game_url)
        add(_("{store}: developer").format(store=label), 'developer', dev_url)

    return links


class PortInfoMixin:
    """
    PortMasterGUI methods: Port details for the template data: images, info and installed size.
    """

    def get_port_image(self, port_name):
        image = None
        if self.hm is not None:
            image = self.hm.port_images(port_name)

            if image is not None:
                image = image.get('screenshot', None)

        if image is None:
            image = "NO_IMAGE"

        return image

    def get_port_links(self, port_name, port_info):
        """port_links() for a port, with the website link if it's from an official source."""
        website = False
        official_urls = set(harbourmaster.HarbourMaster.LEGACY_SOURCE_URLS.values())
        for source in getattr(self.hm, 'sources', {}).values():
            if source._config.get('url') in official_urls and source.clean_name(port_name) in source.ports:
                website = True
                break

        return port_links(port_name, port_info, website=website)

    def set_port_info(self, port_name, port_info, want_install_size=False):
        ## TODO: make this better :D
        if port_name is None:
            self.set_data("port_info.name", "NOTHING")
            self.set_data("port_info.image", "NO_IMAGE")
            self.set_data("port_info.title", _("** NO PORT **"))
            self.set_data("port_info.description", "")
            self.set_data("port_info.instructions", "")
            self.set_data("port_info.genres", "")
            self.set_data("port_info.porter", "")
            self.set_data("port_info.ready_to_run", "")
            self.set_data("port_info.runtime", "")
            self.set_data("port_info.download_size", "")
            self.set_data("port_info.install_size", "")
            self.set_data("port_info.links", "")
            # self.set_data("port_info.image", "no-image")
            return

        self.set_data("port_info.name", port_name)
        self.set_data("port_info.image", str(self.get_port_image(port_name)))
        self.set_data("port_info.title", port_info['attr']['title'])
        self.set_data("port_info.description", port_info['attr']['desc'])
        self.set_data("port_info.instructions", port_info['attr']['inst'])
        self.set_data("port_info.genres", ', '.join(port_info['attr']['genres']))
        self.set_data("port_info.porter", harbourmaster.oc_join(port_info['attr']['porter']))
        self.set_data("port_info.ready_to_run", port_info['attr']['rtr'] and _("Ready to Run") or _("Requires Files"))
        ## How many links the port has (empty for none, for {if:port_info.links}).
        links = len(self.get_port_links(port_name, port_info))
        self.set_data("port_info.links", links and str(links) or "")
        # self.set_data("port_info.image", port_image)

        runtimes = port_info['attr']['runtime']
        if len(runtimes) > 0:
            self.set_data("port_info.runtime", harbourmaster.runtime_nicename(runtimes))
            installed_runtimes = 0
            for runtime in runtimes:
                if (self.hm.libs_dir / runtime).is_file():
                    installed_runtimes += 1

            if len(runtimes) == installed_runtimes:
                self.set_data("port_info.runtime_status", _("Installed"))
            else:
                self.set_data("port_info.runtime_status", _("Missing"))

        else:
            self.set_data("port_info.runtime", "")
            self.set_data("port_info.runtime_status", _("N/A"))

        self.set_data("port_info.download_size", harbourmaster.nice_size(self.hm.port_download_size(port_name)))
        if want_install_size and 'files' in port_info and port_info['files'] is not None:
            self.get_port_size(port_name, port_info)
        else:
            self.set_data("port_info.install_size", "")

        # print(f"INFO: {port_info}")

    def set_theme_info(self, theme_name, theme_info):
        ## TODO: make this better :D
        if theme_name is None:
            self.set_data("theme_info.image", "NO_IMAGE")
            self.set_data("theme_info.name", "")
            self.set_data("theme_info.description", "")
            self.set_data("theme_info.creator", "")
            self.set_data("theme_info.status", "")
            return

        status_to_lang = {
            "Installed": _("Installed"),
            "Update Available": _("Update Available"),
            "Not Installed": _("Not Installed"),
            }

        self.set_data("theme_info.image", str(theme_info['image'] or "NO_IMAGE"))
        self.set_data("theme_info.name", theme_info['name'])
        self.set_data("theme_info.description", theme_info['description'])
        self.set_data("theme_info.creator", theme_info['creator'])
        self.set_data("theme_info.status", status_to_lang.get(theme_info['status'], theme_info['status']))

    def get_port_size(self, port_name, port_info):
        self.port_size_active_port = port_name

        if port_name not in self.port_size_files:
            if port_info is None:
                # HRMMMMMmmmmmm
                return

            self.port_size_files[port_name] = {}

            ports_dir = harbourmaster.HM_PORTS_DIR
            for file_name in port_info['files']:
                if file_name == 'port.json':
                    continue

                full_file_name = ports_dir / file_name
                if not full_file_name.is_absolute():
                    full_file_name = full_file_name.resolve()

                lookup = self.port_size_file_lookup.setdefault(full_file_name, [])
                if port_name not in lookup:
                    lookup.append(port_name)

                if full_file_name.is_file():
                    self.port_size_files[port_name][full_file_name] = [os.stat(full_file_name).st_size, True]

                else:
                    result = self.dir_scanner.check_directory(full_file_name, False)
                    if result is None:
                        self.port_size_files[port_name][full_file_name] = [0, False]
                    else:
                        self.port_size_files[port_name][full_file_name] = [result, True]

        port_size = 0
        all_found = True
        for port_size_info in self.port_size_files[port_name].values():
            port_size += port_size_info[0]
            if not port_size_info[1]:
                all_found = False

        # print(f"PN: {port_name}")
        if not all_found:
            self.set_data("port_info.install_size", f"~ {harbourmaster.nice_size(port_size)}")

        else:
            self.set_data("port_info.install_size", harbourmaster.nice_size(port_size))

    def delete_port_size(self, port_name):
        # Delete info about a port
        if port_name in self.port_size_files:
            for port_file, port_info in self.port_size_files[port_name].items():
                if port_name in self.port_size_file_lookup[port_file]:
                    self.port_size_file_lookup[port_file].remove(port_name)

            del self.port_size_files[port_name]

    def clear_port_sizes(self):
        self.port_size_file_lookup.clear()
        self.port_size_files.clear()
        self.port_size_active_port = None

    def dir_scanner_callback(self, scan_dir, dir_size, is_final=False):
        # print(f"SCAN: {scan_dir}: {dir_size}, {is_final}")
        if scan_dir in self.port_size_file_lookup:
            for port_name in self.port_size_file_lookup[scan_dir]:
                self.port_size_files[port_name][scan_dir][0] = dir_size
                self.port_size_files[port_name][scan_dir][1] = is_final

                if port_name == self.port_size_active_port:
                    self.get_port_size(port_name, None)
