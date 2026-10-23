# SPDX-License-Identifier: MIT
#
# The theme editor: runs the theme preview server (pylibs/theme_server) on the device and
# shows its address, as text and as a QR code, until B stops it.

import json
import os
import random
import subprocess
import sys
import threading

from loguru import logger

from harbourmaster.i18n import _
from pugwash import PYLIB_PATH, lang
from pugwash.util import get_ip_address
from .base import BaseScene


## The dynamic (private) port range: never assigned to a service, so no CFW's own daemons
## are listening on it. Each device picks a random one and keeps it, so the address stays
## the same between sessions; if it's taken, the server takes any free port and that's kept.
PORT_RANGE = (49152, 65535)
## Render processes are 60-90 MB each: as many as the free memory allows, up to this.
MAX_WORKERS = 4


def worker_count(meminfo="/proc/meminfo"):
    """Render processes for the free memory, keeping ~150 MB back."""
    try:
        with open(meminfo) as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    available_mb = int(line.split()[1]) // 1024
                    return max(1, min(MAX_WORKERS, (available_mb - 150) // 100))
    except (OSError, ValueError, IndexError):
        pass

    return 2


def server_port(cfg_data):
    """The port this device used last time, or a random one the first time."""
    port = cfg_data.get('theme_server_port')
    if isinstance(port, bool) or not isinstance(port, int) or not PORT_RANGE[0] <= port <= PORT_RANGE[1]:
        port = random.randint(*PORT_RANGE)

    return port


def fallback_section():
    """For themes without a "theme_server" section: plain, in PortMaster's own font for the
    language (the default theme's "font[ja_JP]" & co), as the address has to be readable."""
    font = "DejaVuSans.ttf"
    try:
        with open(str(PYLIB_PATH / "default_theme" / "theme.json"), encoding="utf-8") as fh:
            base = json.load(fh).get("#base", {})
        font = base.get(f"font[{lang.CURRENT_LANG}]") or base.get("font") or font
    except (OSError, ValueError, AttributeError):
        pass

    text = {"font": font, "font-color": "#e8e8ec", "font-size": 18}
    return {
        "background": {"area": [0.0, 0.0, 1.0, 1.0], "fill": "#1c1c22"},
        "server_title": {**text, "area": [0.05, 0.02, 0.95, 0.12], "font-size": 26, "align": "center",
                         "text": "{scene.title}"},
        "server_qr": {"area": [0.05, 0.15, 0.45, 0.85], "image": "qr:{theme_server.url}", "image-mode": "fit"},
        "server_info": {**text, "area": [0.5, 0.15, 0.95, 0.9], "text-wrap": True, "text": "{theme_server.status}"},
        }


class ThemeServerScene(BaseScene):
    def __init__(self, gui, start=True):
        """start=False: only the screen (the theme server's own preview of it)."""
        super().__init__(gui)
        self.scene_title = _("Theme Editor")
        self.proc = None
        self.url = None
        self.stopped = False

        if "theme_server" not in self.gui.theme_data:
            self.gui.theme_data["theme_server"] = fallback_section()

        self.gui.set_data("theme_server.url", "")
        self.gui.set_data("theme_server.status", _("Starting the theme editor..."))
        self.load_regions("theme_server", [])
        self.set_buttons({'B': _('Stop')})
        if start:
            self.start()

    def start(self):
        hm = self.gui.hm
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join([str(PYLIB_PATH), str(PYLIB_PATH.parent / "exlibs")])
        command = [
            sys.executable, "-m", "theme_server.serve", "--managed",
            "--host", "0.0.0.0", "--port", str(server_port(hm.cfg_data)), "--try-ports", "20", "--any-port",
            "--themes", str(hm.themes_dir),
            "--ports-config", str(hm.cfg_dir),
            "--max-workers", str(worker_count()),
            ]

        ## Next to pugwash.txt.
        log_file = hm.cfg_dir.parent / "theme_server.txt"
        try:
            with open(str(log_file), "w") as log:
                self.proc = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                    env=env, universal_newlines=True)

        except OSError as err:
            logger.error(f"Unable to start the theme editor: {err}")
            self.started({'ok': False, 'error': str(err)})
            return

        proc = self.proc

        def wait_until_ready():
            line = proc.stdout.readline()
            try:
                status = json.loads(line) if line else {'ok': False, 'error': _("it stopped")}
            except ValueError:
                status = {'ok': False, 'error': line.strip()}
            self.gui.dispatcher.post(self.started, status)

        threading.Thread(target=wait_until_ready, name="theme-server", daemon=True).start()

    def started(self, status):
        if self.stopped:
            return

        if not status.get('ok'):
            logger.error(f"Theme editor: {status.get('error')}")
            self.gui.set_data("theme_server.status", _("Unable to start the theme editor: {error}").format(
                error=status.get('error', "")))
            self.stop()
            return

        ## Kept for next time (it was random, or the old one was busy).
        if self.gui.hm.cfg_data.get('theme_server_port') != status['port']:
            self.gui.hm.cfg_data['theme_server_port'] = status['port']
            self.gui.hm.save_config()

        ip_address = get_ip_address(force_update=True)
        if ip_address is None:
            self.gui.set_data("theme_server.status", _(
                "The theme editor is running, but this device isn't on a network. Connect it to Wi-Fi, then start the theme editor again."))
            return

        self.show(f"http://{ip_address}:{status['port']}/")

    def show(self, url):
        self.url = url
        self.gui.set_data("theme_server.url", url)
        self.gui.set_data("theme_server.status", _(
            "On a computer or phone on the same network, scan the code or open:\n\n{url}\n\n"
            "Preview themes at any screen size, and edit PortMaster's translations: they are saved on this device.\n\n"
            "Press B to stop the theme editor.").format(url=url))

    def stop(self):
        """Closing its stdin stops the server; a thread makes sure it does."""
        self.stopped = True
        proc, self.proc = self.proc, None
        if proc is None:
            return

        def wait():
            try:
                proc.stdin.close()
                proc.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()

        threading.Thread(target=wait, name="theme-server-stop", daemon=True).start()

    def do_update(self, events):
        super().do_update(events)

        if self.proc is not None and self.url is not None and self.proc.poll() is not None:
            logger.error(f"Theme editor stopped: {self.proc.returncode}")
            self.proc = None
            self.url = None
            self.gui.set_data("theme_server.url", "")
            self.gui.set_data("theme_server.status", _("The theme editor stopped. See theme_server.txt in the PortMaster folder."))

        if events.was_pressed('B'):
            self.button_back()
            self.stop()
            self.gui.pop_scene()
            return True

        return False
