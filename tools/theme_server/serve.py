#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# The theme dev server: renders every PortMaster screen with your theme, at any resolution,
# colour scheme and language, and shows them in a web page that refreshes when you save.
#
#   python3 tools/theme_server/serve.py --themes DIR [--port 8090]
#       DIR is a theme (it has a theme.json) or a folder of themes. The built-in default
#       theme is always there too. Then open http://localhost:8090/
#
#   python3 tools/theme_server/serve.py --themes DIR --export OUT
#           [--theme NAME] [--resolutions 640x480,1280x720] [--schemes all] [--langs en_US]
#       Writes OUT/<theme>/<resolution>/<scheme>/<lang>/<screen>.png and .json, no server.
#
#   --refresh-ports downloads the ports list and screenshots again (they're cached in
#   ~/.cache/portmaster-theme-server, or --cache DIR).
#
# Needs what running pugwash from a checkout needs (SDL2: pip install pysdl2-dll on macOS)
# and the network the first time, for the real ports list.

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_DIR = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import i18n as i18n_tool  # noqa: E402  (tools/i18n.py)

PM_DIR = REPO_DIR / "PortMaster"
DEFAULT_THEME_DIR = PM_DIR / "pylibs" / "default_theme"
WORKER = HERE / "worker.py"

RESOLUTIONS = (
    "480x320", "640x480", "720x480", "720x720", "854x480", "960x544", "960x720",
    "1024x768", "1280x720", "1280x800", "1920x1080", "1920x1152",
    )

## Render processes kept running at once (each is a pugwash, ~60 MB).
MAX_WORKERS = 6


def default_cache():
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "portmaster-theme-server"


def valid_resolution(text):
    match = re.match(r"^(\d{2,4})x(\d{2,4})$", text or "")
    return bool(match) and 0 < int(match.group(1)) <= 4096 and 0 < int(match.group(2)) <= 4096


################################################################################
## Themes and languages
class Themes:
    """The themes the server shows: the default theme, then each theme in --themes."""
    def __init__(self, themes_dir):
        self.themes_dir = Path(themes_dir).resolve() if themes_dir else None

    def all(self):
        found = {"default_theme": DEFAULT_THEME_DIR}
        if self.themes_dir is not None:
            if (self.themes_dir / "theme.json").is_file():
                found[self.themes_dir.name] = self.themes_dir
            elif self.themes_dir.is_dir():
                for theme_file in sorted(self.themes_dir.glob("*/theme.json")):
                    found[theme_file.parent.name] = theme_file.parent

        return found

    def get(self, theme_id):
        return self.all().get(theme_id)

    def info(self, theme_id, theme_dir):
        """Name, schemes and the default scheme, or the error reading theme.json."""
        try:
            data = json.loads((theme_dir / "theme.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return {'id': theme_id, 'name': theme_id, 'schemes': [], 'default_scheme': None, 'error': str(error)}

        info = data.get("#info", {})
        schemes = [name for name in data.get("#schemes", {}) if not name.startswith("#")]
        default = info.get("default-scheme")
        if default not in schemes:
            default = schemes[0] if schemes else None

        return {'id': theme_id, 'name': info.get("name") or theme_id, 'creator': info.get("creator", ""),
                'schemes': schemes, 'default_scheme': default, 'error': None}

    @staticmethod
    def fingerprint(theme_dir, extra_files=()):
        """Changes whenever a file in the theme (or one of extra_files) is added, removed or saved."""
        digest = hashlib.md5()
        paths = []
        for root, dirs, files in os.walk(str(theme_dir)):
            dirs.sort()
            paths += [os.path.join(root, name) for name in sorted(files)]

        for path in paths + [str(path) for path in extra_files]:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            digest.update(f"{path}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8", "replace"))

        return digest.hexdigest()[:12]


def version(theme_dir, lang):
    """The theme's fingerprint with the language's translation files: what a render depends on."""
    return Themes.fingerprint(theme_dir, [i18n_tool.domain_file(lang, domain) for domain in i18n_tool.DOMAINS])


def languages():
    """[(code, name)]: the languages pugwash has translations for."""
    text = (PM_DIR / "pylibs" / "pugwash" / "lang.py").read_text(encoding="utf-8")
    names = dict(re.findall(r'"(\w\w_\w\w)": _\("([^"]+)"\)', text))
    locales = PM_DIR / "pylibs" / "locales"
    codes = {"en_US"} | {match.group(1) for match in (re.match(r"^([a-z]{2,3}_[A-Z]{2})\.json$", path.name) for path in locales.glob("*.json")) if match}
    return [(code, names.get(code, code)) for code in names if code in codes] + \
        [(code, code) for code in sorted(codes - set(names))]


################################################################################
## Render workers
class WorkerError(Exception):
    pass


class Worker:
    """One worker.py: a pugwash for one theme version, scheme, resolution and language."""
    def __init__(self, key, theme_dir, scheme, resolution, lang, cache, work):
        self.key = key
        self.lock = threading.Lock()
        self.work = Path(work)
        command = [sys.executable, str(WORKER), "--theme-dir", str(theme_dir), "--resolution", resolution,
                   "--lang", lang, "--cache", str(cache), "--work", str(self.work)]
        if scheme:
            command += ["--scheme", scheme]

        self.log_file = open(str(self.work.with_suffix(".log")), "w")
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.log_file, universal_newlines=True, bufsize=1)
        self.ready = self._read()
        if not self.ready.get('ok'):
            self.stop()
            raise WorkerError(self.ready.get('error') or "the renderer didn't start, see " + str(self.log_file.name))

        self.used = time.monotonic()

    def _read(self):
        line = self.proc.stdout.readline()
        if not line:
            return {'ok': False, 'error': "the renderer stopped, see " + str(self.log_file.name)}
        return json.loads(line)

    def request(self, **command):
        with self.lock:
            if self.proc.poll() is not None:
                raise WorkerError("the renderer stopped, see " + str(self.log_file.name))

            self.used = time.monotonic()
            self.proc.stdin.write(json.dumps(command) + "\n")
            self.proc.stdin.flush()
            return self._read()

    def stop(self):
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write(json.dumps({'cmd': "quit"}) + "\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.proc.kill()
        finally:
            self.log_file.close()
            shutil.rmtree(str(self.work), ignore_errors=True)
            try:
                os.unlink(self.log_file.name)
            except OSError:
                pass


class RenderPool:
    """Starts workers as they're needed, replaces them when their theme changes, and caches
    what they rendered."""
    def __init__(self, themes, cache, work_dir):
        self.themes = themes
        self.cache = cache
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.workers = {}
        self.renders = {}
        self.lock = threading.Lock()
        self.start_lock = threading.Lock()
        self.translations = Translations()
        self.counter = 0

    def _worker(self, theme_id, scheme, resolution, lang):
        theme_dir = self.themes.get(theme_id)
        if theme_dir is None:
            raise WorkerError(f"no theme {theme_id!r}")

        fingerprint = version(theme_dir, lang)
        key = (theme_id, fingerprint, scheme or "", resolution, lang)
        with self.lock:
            worker = self.workers.get(key)
        if worker is not None:
            return worker, fingerprint

        ## One start at a time: the page asks for every screen at once.
        with self.start_lock:
            with self.lock:
                worker = self.workers.get(key)
                if worker is not None:
                    return worker, fingerprint

                ## The same settings for an older version of the theme, then the least
                ## recently used if there are too many.
                stale = [self.workers.pop(other) for other in list(self.workers)
                         if other[0] == theme_id and other[2:] == key[2:]]
                while len(self.workers) >= MAX_WORKERS:
                    stale.append(self.workers.pop(min(self.workers, key=lambda other: self.workers[other].used)))

                self.counter += 1
                work = self.work_dir / f"worker-{self.counter}"

            for old in stale:
                old.stop()

            worker = Worker(key, theme_dir, scheme, resolution, lang, self.cache, work)
            with self.lock:
                self.workers[key] = worker

        return worker, fingerprint

    def render(self, theme_id, scheme, resolution, lang, shot):
        """(png bytes, info dict) for one screen, cached until the theme changes."""
        worker, fingerprint = self._worker(theme_id, scheme, resolution, lang)
        render_key = worker.key + (shot,)
        with self.lock:
            if render_key in self.renders:
                return self.renders[render_key]

        out_file = worker.work / f"{shot}.png"
        answer = worker.request(cmd="render", shot=shot, out=str(out_file))
        if not answer.get('ok'):
            raise WorkerError(answer.get('error', "render failed"))

        png = out_file.read_bytes() if not answer.get('missing') else b""
        info = {
            'shot': shot, 'theme': theme_id, 'scheme': worker.ready.get('scheme'), 'resolution': resolution,
            'lang': lang, 'version': fingerprint, 'regions': answer.get('regions', []),
            'errors': answer.get('errors', []), 'missing': answer.get('missing'), 'ms': answer.get('ms'),
            'strings': self.translations.used(answer.get('strings', {})),
            }
        with self.lock:
            ## Drop renders of older versions of the theme and the language's translations.
            for old_key in [k for k in self.renders if k[0] == theme_id and k[4] == lang and k[1] != fingerprint]:
                del self.renders[old_key]
            self.renders[render_key] = (png, info)

        return png, info

    def shots(self):
        worker, _ = self._worker("default_theme", None, "640x480", "en_US")
        return worker.request(cmd="shots")['shots']

    def stop(self):
        with self.lock:
            workers, self.workers = list(self.workers.values()), {}
        for worker in workers:
            worker.stop()


################################################################################
## Translations: the language files in the checkout's PortMaster/pylibs/locales
class Translations:
    """Reads and saves translations, one string at a time."""
    def __init__(self):
        self.lock = threading.Lock()

    def strings(self):
        return i18n_tool.read_strings()

    def used(self, lookups):
        """The strings a render looked up that are translatable (not {templates} and the like)."""
        strings = self.strings()
        return {domain: [text for text in lookups.get(domain, []) if text in strings[domain]] for domain in i18n_tool.DOMAINS}

    def language(self, lang):
        """Every string of both domains, with this language's translation and its problems."""
        strings, translations = self.strings(), i18n_tool.read_translations(lang)
        result = {}
        for domain in i18n_tool.DOMAINS:
            entries = []
            for text, sources in strings[domain].items():
                translation = translations[domain].get(text, "")
                entries.append({'text': text, 'translation': translation, 'sources': sources,
                                'problems': i18n_tool.problems(text, translation) if translation else []})
            result[domain] = entries
        return result

    def save(self, lang, domain, text, translation):
        """Sets one translation ("" removes it), in strings.json's order. Returns its problems."""
        with self.lock:
            strings = self.strings()[domain]
            if text not in strings:
                raise KeyError(text)

            translations = i18n_tool.read_translations(lang)[domain]
            if translation:
                translations[text] = translation
            else:
                translations.pop(text, None)

            ordered = {key: translations[key] for key in strings if key in translations}
            path = i18n_tool.domain_file(lang, domain)
            temp = path.with_name(path.name + ".tmp")
            i18n_tool.write_json(temp, ordered)
            os.replace(str(temp), str(path))
            ## Both files of a language exist once it has one.
            for other in i18n_tool.DOMAINS:
                if not i18n_tool.domain_file(lang, other).exists():
                    i18n_tool.write_json(i18n_tool.domain_file(lang, other), {})

        return i18n_tool.problems(text, translation) if translation else []


def all_languages():
    """[(code, name, has files)]: every language PortMaster knows a name for, and any other with files."""
    have = {code for code, _ in languages()}
    text = (PM_DIR / "pylibs" / "pugwash" / "lang.py").read_text(encoding="utf-8")
    names = dict(re.findall(r'"(\w\w_\w\w)": _\("([^"]+)"\)', text))
    return [(code, names.get(code, code), code in have) for code in sorted(set(names) | have, key=lambda code: names.get(code, code))]


################################################################################
## The Chinese, Japanese and Korean fonts: the PortMaster/pugwash script unpacks them on
## its first run, the workers import pugwash without it.
def ensure_fonts():
    resources = PM_DIR / "pylibs" / "resources"
    if (resources / "NotoSansTC-Regular.ttf").is_file():
        return

    try:
        with tarfile.open(str(resources / "NotoSans.tar.xz"), "r:xz") as tar:
            tar.extractall(str(resources))

    except (OSError, EOFError, tarfile.TarError) as err:
        print(f"Unable to extract the Noto fonts, Chinese, Japanese and Korean won't show: {err}")


################################################################################
## The ports cache
def ensure_cache(cache, refresh=False):
    source = cache / "tools" / "PortMaster" / "config" / "020_portmaster.source.json"
    if source.is_file() and not refresh:
        try:
            if json.loads(source.read_text()).get('data', {}).get('ports'):
                return
        except ValueError:
            pass

    print(f"Downloading the ports list and screenshots into {cache} ...", flush=True)
    if (cache / "tools").exists():
        shutil.rmtree(str(cache / "tools"))

    result = subprocess.run([sys.executable, str(WORKER), "--prepare-cache", str(cache)])
    if result.returncode != 0:
        sys.exit("Couldn't download the ports list (no network?). Screens will show no ports.")


################################################################################
## The web server
class Handler(BaseHTTPRequestHandler):
    server_version = "PortMasterThemeServer/1"

    def log_message(self, format, *args):
        if self.server.verbose:
            super().log_message(format, *args)

    def send(self, status, body, content_type="application/json", cache=False):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = {key: values[-1] for key, values in urllib.parse.parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                self.send(200, (HERE / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")

            elif url.path == "/api/info":
                themes = self.server.themes
                self.send(200, {
                    'themes': [themes.info(theme_id, theme_dir) for theme_id, theme_dir in themes.all().items()],
                    'languages': languages(),
                    'resolutions': list(RESOLUTIONS),
                    'shots': self.server.shots,
                    'all_languages': all_languages(),
                    })

            elif url.path == "/api/strings":
                lang = query.get('lang', "")
                if not re.match(r"^[a-z]{2,3}_[A-Z]{2}$", lang):
                    self.send(400, {'error': "bad language"})
                    return
                self.send(200, {'lang': lang, 'domains': self.server.pool.translations.language(lang)})

            elif url.path == "/api/version":
                theme_dir = self.server.themes.get(query.get('theme'))
                lang = query.get('lang', "en_US")
                if not re.match(r"^[a-z]{2,3}_[A-Z]{2}$", lang):
                    self.send(400, {'error': "bad language"})
                    return
                self.send(200 if theme_dir else 404, {'version': version(theme_dir, lang) if theme_dir else None})

            elif url.path in ("/api/render.png", "/api/render.json"):
                theme_id = query.get('theme', "default_theme")
                resolution = query.get('res', "640x480")
                lang = query.get('lang', "en_US")
                shot = query.get('shot', "main_menu")
                if not valid_resolution(resolution) or not re.match(r"^\w\w_\w\w$", lang) or \
                        shot not in {name for name, _ in self.server.shots}:
                    self.send(400, {'error': "bad theme, resolution, language or screen"})
                    return

                png, info = self.server.pool.render(theme_id, query.get('scheme') or None, resolution, lang, shot)
                if url.path.endswith(".png"):
                    if not png:
                        self.send(404, {'error': info['missing']})
                    else:
                        ## The URL carries the theme version, so it can be cached.
                        self.send(200, png, "image/png", cache='v' in query)
                else:
                    self.send(200, info)

            else:
                self.send(404, {'error': "not found"})

        except WorkerError as error:
            self.send(500, {'error': str(error)})

        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        ## Only the page itself: another site can't send this header without a CORS
        ## preflight, which this server never answers.
        if self.headers.get("X-Theme-Server") != "1" or not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self.send(403, {'error': "forbidden"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= 256 * 1024:
                self.send(400, {'error': "bad request"})
                return
            body = json.loads(self.rfile.read(length).decode("utf-8"))

            if url.path == "/api/translate":
                lang, domain = body.get('lang', ""), body.get('domain', "")
                text, translation = body.get('text'), body.get('translation', "")
                if not re.match(r"^[a-z]{2,3}_[A-Z]{2}$", lang) or lang == "en_US" or domain not in i18n_tool.DOMAINS or \
                        not isinstance(text, str) or not isinstance(translation, str):
                    self.send(400, {'error': "bad language, domain or text"})
                    return
                try:
                    problems = self.server.pool.translations.save(lang, domain, text, translation)
                except KeyError:
                    self.send(404, {'error': "not a translatable string"})
                    return
                self.send(200, {'ok': True, 'problems': problems})

            else:
                self.send(404, {'error': "not found"})

        except (ValueError, UnicodeDecodeError, AttributeError):
            self.send(400, {'error': "bad request"})

        except (BrokenPipeError, ConnectionResetError):
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True


################################################################################
## Export
def export(pool, themes, out, theme_ids, resolutions, schemes, langs, shots):
    failures = 0
    for theme_id in theme_ids:
        info = themes.info(theme_id, themes.get(theme_id))
        theme_schemes = info['schemes'] if schemes == ["all"] else (schemes or [info['default_scheme']])
        for resolution in resolutions:
            for scheme in theme_schemes or [None]:
                for lang in langs:
                    folder = out / theme_id / resolution / (scheme or "default") / lang
                    folder.mkdir(parents=True, exist_ok=True)
                    for shot, _ in shots:
                        try:
                            png, info = pool.render(theme_id, scheme, resolution, lang, shot)
                        except WorkerError as error:
                            print(f"FAIL {theme_id} {resolution} {scheme} {lang} {shot}: {error}", file=sys.stderr)
                            failures += 1
                            continue

                        if png:
                            (folder / f"{shot}.png").write_bytes(png)
                        (folder / f"{shot}.json").write_text(json.dumps(info, indent=1))
                        for error in info['errors']:
                            print(f"{theme_id} {resolution} {scheme} {lang} {shot}: {error}", file=sys.stderr)

                    print(f"{folder}", flush=True)

    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Renders PortMaster's screens with your theme.")
    parser.add_argument("--themes", help="a theme folder, or a folder of themes")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to let other machines connect")
    parser.add_argument("--cache", type=Path, default=default_cache())
    parser.add_argument("--refresh-ports", action="store_true", help="download the ports list and screenshots again")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--export", type=Path, metavar="OUT", help="write PNGs instead of serving them")
    parser.add_argument("--theme", action="append", help="export: these themes (default: all)")
    parser.add_argument("--resolutions", default="640x480", help="export: comma separated, or 'all'")
    parser.add_argument("--schemes", default="", help="export: comma separated, 'all', or the theme's default")
    parser.add_argument("--langs", default="en_US", help="export: comma separated")
    options = parser.parse_args(argv)

    ensure_fonts()
    ensure_cache(options.cache, options.refresh_ports)
    themes = Themes(options.themes)
    work_dir = Path(tempfile.mkdtemp(prefix="pm-theme-server-"))
    pool = RenderPool(themes, options.cache, work_dir)

    try:
        shots = pool.shots()
        if options.export:
            resolutions = list(RESOLUTIONS) if options.resolutions == "all" else options.resolutions.split(",")
            bad = [resolution for resolution in resolutions if not valid_resolution(resolution)]
            if bad:
                sys.exit(f"Not a resolution: {', '.join(bad)}")

            return export(pool, themes, options.export, options.theme or list(themes.all()), resolutions,
                          [scheme for scheme in options.schemes.split(",") if scheme], options.langs.split(","), shots)

        try:
            server = Server((options.host, options.port), Handler)
        except OSError as error:
            sys.exit(f"Can't listen on {options.host}:{options.port} ({error.strerror}), try another --port.")

        server.themes, server.pool, server.shots, server.verbose = themes, pool, shots, options.verbose
        print(f"Theme server on http://{'localhost' if options.host == '127.0.0.1' else options.host}:{options.port}/"
              f" ({len(themes.all())} theme{'s' if len(themes.all()) != 1 else ''}), Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    finally:
        pool.stop()
        shutil.rmtree(str(work_dir), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
