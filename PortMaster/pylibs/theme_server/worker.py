#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# The theme dev server's renderer: a headless pugwash that draws one scene at a time.
#
# SDL allows one GUI per process, and the screen size, the theme's [hires]/[4:3] overrides
# and the language are fixed when pugwash starts, so serve.py runs one of these for each
# theme, colour scheme, resolution and language, and starts a new one when the theme's
# files change. Commands are JSON lines on stdin, answers JSON lines on stdout; anything
# else pugwash prints goes to stderr.
#
#   worker.py --theme-dir DIR --resolution 640x480 [--scheme NAME] [--lang en_US]
#             --ports-config DIR --work DIR
#
#   --ports-config is a PortMaster config folder with the ports list and screenshots: the
#   cache's (DIR/tools/PortMaster/config, see --prepare-cache), or on a device PortMaster's
#   own. Nothing in it is changed.
#
#   {"cmd": "load", "theme_dir": DIR, "scheme": NAME or null, "lang": "de_DE"}
#       -> {"ok": true, "theme": name, "scheme": ...}: switches theme, scheme and language
#       in place (or reloads them after a save), about a second instead of a new renderer.
#   {"cmd": "render", "shot": "main_menu", "out": "/tmp/x.png"}
#       -> {"ok": true, "regions": [...], "errors": [...]}
#   {"cmd": "shots"} -> {"ok": true, "shots": [[name, title], ...]}
#   {"cmd": "quit"}
#
#   worker.py --prepare-cache DIR
#       Downloads the PortMaster sources (ports.json, port screenshots, featured ports)
#       into DIR/tools/PortMaster/config, where every renderer finds them.

import argparse
import json
import math
import os
import shutil
import sys
import time
import traceback
from pathlib import Path


## PortMaster/pylibs/theme_server/worker.py
PM_DIR = Path(__file__).resolve().parents[2]


def screen_capabilities(width, height):
    """The screen capabilities device_info.txt gives a device with this screen."""
    gcd = math.gcd(width, height) or 1
    aspect_x, aspect_y = width // gcd, height // gcd
    if (aspect_x, aspect_y) == (8, 5):
        aspect_x, aspect_y = 16, 10

    caps = [f"{width}x{height}", f"{aspect_x}:{aspect_y}"]
    if (aspect_x, aspect_y) == (16, 10):
        caps.append("16:9")

    if width >= 960 or height >= 720:
        caps.append("hires")
    elif width < 640 or height < 480:
        caps.append("lowres")

    if aspect_x >= 16 or aspect_x * 10 // aspect_y >= 15:
        caps.append("wide")
    elif aspect_x == aspect_y:
        caps.append("square")

    return caps


def device_env(width, height, lang):
    """A pretend aarch64 device with this screen, as the env device_info.txt would write."""
    caps = ["aarch64", "armhf", "power", "opengl", "2gb", "1gb", "analog_0", "analog_1", "analog_2"]
    caps += screen_capabilities(width, height)
    return {
        'DEVICE_NAME': "Theme Preview",
        'DEVICE_CPU': "rk3566",
        'DEVICE_ARCH': "aarch64",
        'DEVICE_RAM': "2",
        'CFW_NAME': "PortMaster",
        'CFW_VERSION': "theme-server",
        'DISPLAY_WIDTH': str(width),
        'DISPLAY_HEIGHT': str(height),
        'ANALOG_STICKS': "2",
        'DEVICE_CAPABILITIES': " ".join(caps),
        'PM_PRETEND_RESOLUTION': f"{width}x{height}",
        'LANG': lang,
        }


def sdl_env():
    """Headless pugwash: no window or video driver, it draws onto a surface (PM_HEADLESS),
    so it runs on SDL builds with no dummy driver and next to a GUI that owns the screen."""
    return {'PM_HEADLESS': "Y", 'SDL_AUDIODRIVER': "dummy"}


def prepare_tools_dir(work, ports_config, theme_dir, scheme):
    """work/tools: the ports data from ports_config (files copied, the screenshot folders
    linked: harbourmaster may rewrite a source file, it only reads the screenshots), the
    theme, and a config.json."""
    tools = work / "tools"
    config = tools / "PortMaster" / "config"
    if tools.exists():
        shutil.rmtree(str(tools))

    config.mkdir(parents=True)
    (tools / "PortMaster" / "themes").mkdir()
    (tools / "PortMaster" / "libs").mkdir()
    (work / "ports").mkdir(exist_ok=True)
    (work / "temp").mkdir(exist_ok=True)

    cached = Path(ports_config)
    if cached.is_dir():
        for entry in cached.iterdir():
            if entry.name == "config.json":
                continue
            if entry.is_dir():
                (config / entry.name).symlink_to(entry.resolve())
            elif entry.is_file():
                shutil.copyfile(str(entry), str(config / entry.name))

    theme_name = link_theme(tools / "PortMaster" / "themes", theme_dir)

    ## Its "version", else harbourmaster upgrades the config by deleting the image folders
    ## (here links), and not a first run, which writes the default sources.
    cfg_data = {}
    try:
        cfg_data = json.loads((cached / "config.json").read_text())
    except (OSError, ValueError):
        pass

    (config / "config.json").write_text(json.dumps({
        **{key: cfg_data[key] for key in ('version',) if key in cfg_data},
        'first-run': False,
        'theme': theme_name,
        'theme-scheme': scheme,
        'disclaimer': True,
        'warning_time': "9999-12-31",
        'sfx-disabled': True,
        'music-disabled': True,
        }, indent=2))

    return theme_name


def link_theme(themes_dir, theme_dir):
    """The theme's name, linked into themes_dir (PortMaster/themes) unless it's the built-in one."""
    default_theme = PM_DIR / "pylibs" / "default_theme"
    target = Path(theme_dir).resolve()
    if target == default_theme.resolve():
        return "default_theme"

    link = Path(themes_dir) / target.name
    if link.is_symlink() and Path(os.readlink(str(link))) == target:
        return target.name
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(target)
    return target.name


def prepare_cache(cache):
    """Fill the cache like a first PortMaster start online would, then exit."""
    cache = Path(cache)
    for name in ("tools", "ports", "temp"):
        (cache / name).mkdir(parents=True, exist_ok=True)

    os.environ['HM_TOOLS_DIR'] = str(cache / "tools")
    os.environ['HM_PORTS_DIR'] = str(cache / "ports")
    os.environ['HM_SCRIPTS_DIR'] = str(cache / "ports")
    os.environ.update({key: value for key, value in device_env(640, 480, "en_US").items() if key.startswith(("DEVICE_", "CFW_"))})
    sys.path[:0] = [str(PM_DIR / "pylibs"), str(PM_DIR / "exlibs")]

    import harbourmaster
    from loguru import logger
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    class Progress(harbourmaster.Callback):
        def message(self, message):
            print(message.strip(), file=sys.stderr)

    hm = harbourmaster.HarbourMaster({'offline': False, 'no-check': False},
                                     temp_dir=cache / "temp", callback=Progress())
    hm.featured_ports(pre_load=True)
    counts = {name: len(source.ports) for name, source in hm.sources.items()}
    print(json.dumps({'ok': sum(counts.values()) > 0, 'ports': counts}))
    return 0 if sum(counts.values()) > 0 else 1


def renderer_env(width, height, lang):
    """The environment pugwash and harbourmaster read: the pretend device, headless SDL."""
    os.environ.update(device_env(width, height, lang))
    os.environ.update(sdl_env())
    for key in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES'):
        os.environ.pop(key, None)


def use_tools_dir(work):
    os.environ['HM_TOOLS_DIR'] = str(work / "tools")
    os.environ['HM_PORTS_DIR'] = str(work / "ports")
    os.environ['HM_SCRIPTS_DIR'] = str(work / "ports")


def import_pugwash():
    """Next to PortMaster/ (from a checkout that's harbourmaster's testing mode), then the
    modules: once the environment above is set, they read it on import."""
    os.chdir(str(PM_DIR.parent))
    sys.path[:0] = [str(PM_DIR / "pylibs"), str(PM_DIR / "exlibs")]
    from theme_server import shots
    return shots


def run_renderer(shots, work, theme_dir, scheme, lang, resolution, lines, reply, tools_dir=None):
    """Starts the renderer and answers commands from lines until "quit" or the end."""
    import harbourmaster

    themes_dir = harbourmaster.HM_TOOLS_DIR / "PortMaster" / "themes"
    try:
        theme_name = link_theme(themes_dir, theme_dir)
        renderer = shots.Renderer(work, theme_name, scheme=scheme, tools_dir=tools_dir)

    except Exception:
        reply(ok=False, error=traceback.format_exc())
        return 1

    reply(ok=True, ready=True, resolution=resolution, theme=theme_name, scheme=renderer.scheme)

    for line in lines:
        try:
            command = json.loads(line)
            if command.get('cmd') == "quit":
                break

            elif command.get('cmd') == "shots":
                reply(ok=True, shots=[[name, title] for name, title, _ in shots.SHOTS])

            elif command.get('cmd') == "load":
                started = time.monotonic()
                theme_name = link_theme(themes_dir, command['theme_dir'])
                renderer.load(theme_name, command.get('scheme'), command.get('lang') or lang)
                reply(ok=True, theme=theme_name, scheme=renderer.scheme, ms=int((time.monotonic() - started) * 1000))

            elif command.get('cmd') == "render":
                started = time.monotonic()
                try:
                    regions, errors = renderer.render(command['shot'], command['out'])

                except shots.MissingSection as missing:
                    reply(ok=True, missing=str(missing), regions=[], errors=[])
                    continue

                reply(ok=True, regions=regions, errors=errors, strings=renderer.strings(),
                      ms=int((time.monotonic() - started) * 1000))

            else:
                reply(ok=False, error=f"unknown command {command.get('cmd')!r}")

        except Exception:
            reply(ok=False, error=traceback.format_exc())

    renderer.quit()
    return 0


def json_writer(file):
    def reply(**answer):
        file.write(json.dumps(answer) + "\n")
        file.flush()
    return reply


def parse_resolution(text):
    return [int(part) for part in text.lower().split("x")]


################################################################################
## The zygote: imports pugwash once, then forks a renderer for each screen size, which
## saves the imports (half of a renderer's start) each time.
##
##   worker.py --zygote --control-fd N --ports-config DIR --work DIR
##
## serve.py sends on the control socket a JSON message, with the renderer's end of a
## socket pair attached (SCM_RIGHTS):
##   {"resolution": "640x480", "theme_dir": DIR, "scheme": ..., "lang": ..., "work": DIR}
##   -> {"ok": true, "pid": N}
## The renderer then talks on that socket as a worker.py does on stdin/stdout. The
## zygote stops when its stdin closes.
def zygote(options):
    import array
    import select
    import signal
    import socket

    control = socket.socket(fileno=options.control_fd)
    shared = Path(options.work)
    shared.mkdir(parents=True, exist_ok=True)
    ## The themes (linked as renderers load them) and the config pugwash reads at start;
    ## each renderer's HarbourMaster has its own copy of the ports.
    prepare_tools_dir(shared, Path(options.ports_config), PM_DIR / "pylibs" / "default_theme", None)
    renderer_env(640, 480, "en_US")
    use_tools_dir(shared)
    shots = import_pugwash()
    from harbourmaster import hardware
    from pugwash import lang as pug_lang

    ## Renderers are reaped by the system.
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    send = json_writer(control.makefile("w"))
    send(ok=True, ready=True)

    ## No threads: it forks. Its stdin closing (serve.py gone) stops it.
    fd_size = array.array("i").itemsize
    while True:
        readable, _, _ = select.select([control, 0], [], [])
        if 0 in readable and not os.read(0, 4096):
            return 0
        if control not in readable:
            continue

        data, ancdata, _, _ = control.recvmsg(65536, socket.CMSG_SPACE(fd_size))
        if not data:
            return 0

        fds = array.array("i")
        for level, kind, payload in ancdata:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                fds.frombytes(payload[:len(payload) - (len(payload) % fd_size)])

        try:
            spawn = json.loads(data.decode("utf-8"))
            channel = socket.socket(fileno=fds[0])
        except (ValueError, IndexError, OSError) as error:
            send(ok=False, error=f"bad spawn request: {error}")
            continue

        pid = os.fork()
        if pid == 0:
            ## The renderer.
            code = 1
            try:
                control.close()
                signal.signal(signal.SIGCHLD, signal.SIG_DFL)
                work = Path(spawn['work'])
                work.mkdir(parents=True, exist_ok=True)
                log = open(str(work.with_suffix(".log")), "w")
                os.dup2(log.fileno(), 2)
                os.dup2(log.fileno(), 1)
                devnull = os.open(os.devnull, os.O_RDONLY)
                os.dup2(devnull, 0)

                width, height = parse_resolution(spawn['resolution'])
                prepare_tools_dir(work, Path(options.ports_config), PM_DIR / "pylibs" / "default_theme", None)
                renderer_env(width, height, spawn['lang'])
                hardware._CACHED_DICT = None
                pug_lang.set_language(spawn['lang'])
                code = run_renderer(shots, work, Path(spawn['theme_dir']), spawn.get('scheme'), spawn['lang'],
                                    [width, height], channel.makefile("r"), json_writer(channel.makefile("w")),
                                    tools_dir=work / "tools")
            except BaseException:
                traceback.print_exc()
            finally:
                os._exit(code)

        channel.close()
        send(ok=True, pid=pid)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["--prepare-cache"] and len(argv) == 2:
        return prepare_cache(argv[1])

    parser = argparse.ArgumentParser(description="theme dev server renderer")
    parser.add_argument("--zygote", action="store_true")
    parser.add_argument("--control-fd", type=int)
    parser.add_argument("--theme-dir")
    parser.add_argument("--scheme", default=None)
    parser.add_argument("--resolution", default="640x480")
    parser.add_argument("--lang", default="en_US")
    parser.add_argument("--ports-config", required=True)
    parser.add_argument("--work", required=True)
    options = parser.parse_args(argv)

    if options.zygote:
        return zygote(options)

    ## Answers go to the real stdout, everything pugwash prints to stderr.
    reply = json_writer(os.fdopen(os.dup(1), 'w'))
    os.dup2(2, 1)

    width, height = parse_resolution(options.resolution)
    work = Path(options.work)
    work.mkdir(parents=True, exist_ok=True)
    prepare_tools_dir(work, Path(options.ports_config), PM_DIR / "pylibs" / "default_theme", None)
    renderer_env(width, height, options.lang)
    use_tools_dir(work)
    shots = import_pugwash()
    return run_renderer(shots, work, Path(options.theme_dir), options.scheme, options.lang, [width, height], sys.stdin, reply)


if __name__ == "__main__":
    sys.exit(main())
