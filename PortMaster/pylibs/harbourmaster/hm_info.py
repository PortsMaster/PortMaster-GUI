# SPDX-License-Identifier: MIT

import datetime
import shutil
import zipfile
from gettext import gettext as _
from loguru import logger
from .util import calculate_git_blob_sha_data, calculate_git_blob_sha_file, datetime_compare, download, fetch_data, fetch_text, json_safe_load, json_safe_loads


class InfoMixin:
    """
    HarbourMaster methods: Port info files from PortMaster-Info: ports_info.json, porters.json, stats, featured ports data.
    """

    def ports_info(self):
        if self._PORTS_INFO is None:
            with open(self.cfg_dir / "ports_info.json", 'r') as fh:
                self._PORTS_INFO = json_safe_load(fh)

            if self._PORTS_INFO is None:
               self._PORTS_INFO = {"items": {}, "md5": {}, "ports": {}, "portsmd_fix": {}}

        return self._PORTS_INFO

    def port_downloads(self, port_name):
        if self._PORTS_DOWNLOAD is None:
            port_stats_data = {"ports": {}}

            port_stats = self.cfg_dir / "port_stats.json"
            if port_stats.is_file():
                with port_stats.open('r') as fh:
                    port_stats_data = json_safe_load(fh)

            if isinstance(port_stats_data, dict) and "ports" in port_stats_data:
                self._PORTS_DOWNLOAD = port_stats_data["ports"]
            else:
                self._PORTS_DOWNLOAD = {}

        return self._PORTS_DOWNLOAD.get(port_name, 0)

    def porters(self):
        if self._PORTERS is None:
            with open(self.cfg_dir / "porters.json", 'r') as fh:
                self._PORTERS = json_safe_load(fh)

            if self._PORTERS is None:
               self._PORTERS = {}

        return self._PORTERS

    def load_info_fetch_remote(self, local_file, remote_url, remote_size, sha_source):
        """
        This function is used to fetch a remote file during load_info.
        """

        # Over 1mb we will use a progress bar.
        if remote_size > (1024 * 1024):
            temp_file = download(
                self.temp_dir / local_file.name,
                remote_url,
                callback=self.callback,
                no_check=True)

            if not temp_file:
                # Something fucked up. :|
                return False

            sha_local = calculate_git_blob_sha_file(temp_file)
            if sha_local != sha_source:
                self.callback.message(_("Download validation failed."))
                logger.error(f"File validation failed {sha_local} vs {sha_source}")
                temp_file.unlink()

            if temp_file != local_file:
                shutil.copy2(temp_file, local_file)
                if temp_file.is_file():
                    temp_file.unlink()
            return True

        else:
            file_data = fetch_data(remote_url)

            if file_data is None:
                # Who knows...
                self.callback.message(_("Unable to download file."))
                return False

            sha_local = calculate_git_blob_sha_data(file_data)
            if sha_local != sha_source:
                self.callback.message(_("Download validation failed."))
                logger.error(f"File validation failed {sha_local} vs {sha_source}")
                return False

            with local_file.open("wb") as fh:
                fh.write(file_data)

            return True

    def load_info(self, force_load=False):
        self.callback.message("- {}".format(_("Loading Info.")))
        self.runtimes_info = None

        if self.runtimes_file.is_file():
            ## TODO: double check this shit and redo it.

            with open(self.runtimes_file, 'r') as fh:
                self.runtimes_info = json_safe_load(fh)

            self.list_runtimes()

        if self.runtimes_info is None:
            self.runtimes_info = {}

        # These are the base files, and empty versions that are safe.
        base_check_files = [
            (
                "ports_info.json",
                '{"items": {}, "md5": {}, "ports": {}, "portsmd_fix": {}}',
                _("Fetching latest ports info data.")),
            (
                "porters.json",
                '{}',
                _("Fetching latest porters info.")),
            (
                "port_stats.json",
                '{"ports": {}, "total_downloads": 0}',
                _("Fetching latest port stats.")),
            (
                "featured_ports.json",
                '[]',
                _("Fetching latest featured ports.")),
            (
                "featured_images.zip",
                None, # Doesn't matter if it doesn't exist.
                _("Fetching latest featured port images zip."))
            ]

        # Create empty files for fallback.
        for file_name, base_data, info_message in base_check_files:
            if base_data is None:
                continue

            local_file = self.cfg_dir / file_name
            if local_file.is_file():
                continue

            with open(local_file, 'w') as fh:
                fh.write(base_data)

        # And this for good luck.
        featured_ports_dir  = self.cfg_dir / "featured_ports/"
        if not featured_ports_dir.is_dir():
            featured_ports_dir.mkdir(0o755, exist_ok=True, parents=True)

        # Delete some old config keys.
        if "featured_ports_checked" in self.cfg_data:
            del self.cfg_data["featured_ports_checked"]

        if "porters_checked" in self.cfg_data:
            del self.cfg_data["porters_checked"]

        if "ports_info_checked" in self.cfg_data:
            del self.cfg_data["ports_info_checked"]

        # In offline mode, we're done!
        if self.config['offline'] or self.config['no-check']:
            return

        # Check if we are due to fetch new data.
        TIME_SINCE_CHECK = self.INFO_CHECK_INTERVAL

        if self.cfg_data.get('last-info-check', None) is not None:
            TIME_SINCE_CHECK = datetime_compare(self.cfg_data['last-info-check'])

        # Too soon?
        if TIME_SINCE_CHECK < self.INFO_CHECK_INTERVAL:
            # Too soon.
            return

        # Fetch the github api tree data for the PortMaster-Info repo.
        port_info_json_raw = fetch_text(self.PORT_INFO_JSON)
        if port_info_json_raw is None:
            # Things are broken, probably muOS, put it in offline mode.
            self.config['offline'] = True
            return

        port_info_json = json_safe_loads(port_info_json_raw)
        if port_info_json is None or not isinstance(port_info_json, dict) or 'tree' not in port_info_json:
            logger.error(f"Unable to fetch a sensible version of {self.PORT_INFO_JSON}, aborting: {port_info_json_raw}")
            return

        # Build up the database of the files.
        port_info_info = {}
        for item in port_info_json['tree']:
            if item['type'] != 'blob':
                continue

            if item['path'].startswith('.'):
                continue

            file_name = item['path']

            # Fix featured ports images local path.
            if file_name.startswith('images/'):
                file_name = 'featured_ports/' + file_name.split('/', 1)[-1]

            port_info_info[file_name] = {
                'sha':  item['sha'],
                'size': item['size'],
                'url':  self.PORT_INFO_URL + item['path'],
                'updated': False,
                }

        # Check the base files.
        for file_name, base_data, info_message in base_check_files:
            if file_name not in port_info_info:
                continue

            local_file = self.cfg_dir / file_name

            local_sha = calculate_git_blob_sha_file(local_file)
            logger.debug(f"{file_name}: {local_sha} vs {port_info_info[file_name]['sha']}")
            if local_sha == port_info_info[file_name]['sha']:
                continue

            self.callback.message("  - {}".format(info_message))

            local_file.parent.mkdir(0o755, exist_ok=True, parents=True)

            port_info_info[file_name]['updated'] = self.load_info_fetch_remote(
                local_file,
                port_info_info[file_name]['url'],
                port_info_info[file_name]['size'],
                port_info_info[file_name]['sha'])

        featured_ports_images = {}

        # Extract the featured_images.zip
        if port_info_info.get("featured_images.zip", {}).get("updated", False):
            # Updated featured_images.zip :)
            with zipfile.ZipFile(self.cfg_dir / "featured_images.zip", 'r') as zf:
                logger.info("Extracting featured_images.zip")

                for file_info in zf.infolist():
                    if file_info.filename.endswith('/'):
                        continue

                    # We only want images.
                    if not file_info.filename.endswith(('.png', '.jpg')):
                        continue

                    logger.info(f"- {file_info.filename}")

                    # Force it to only keep the file name, because I don't trust you (or me) to not fuck it up.
                    local_file = featured_ports_dir / file_info.filename.rsplit('/', 1)[-1]
                    featured_ports_images[local_file.name] = True

                    with local_file.open('wb') as fh:
                        fh.write(zf.read(file_info.filename))

        # Hopefully catch any images that weren't in the featured_images.zip
        for file_name in port_info_info:
            if not file_name.startswith('featured_ports/'):
                continue

            if not file_name.endswith(('.png', '.jpg')):
                continue

            local_file = self.cfg_dir / file_name

            # Skip ones that were just extracted in the zip file.
            if featured_ports_images.get(local_file.name):
                continue

            local_sha = calculate_git_blob_sha_file(local_file)
            logger.debug(f"{file_name}: {local_sha} vs {port_info_info[file_name]['sha']}")
            if local_sha == port_info_info[file_name]['sha']:
                continue

            self.callback.message("  - {}".format(_("Fetching featured port image {file_name}").format(file_name=local_file.name)))

            port_info_info[file_name]['updated'] = self.load_info_fetch_remote(
                local_file,
                port_info_info[file_name]['url'],
                port_info_info[file_name]['size'],
                port_info_info[file_name]['sha'])

        # Check the featured_ports.json
        # if port_info_info.get("featured_ports.json", {}).get("updated", False):
        #     self.featured_ports()

        self.cfg_data['last-info-check'] = datetime.datetime.now().isoformat()

        return

    def porters_list(self):
        return list(self.porters().keys())
