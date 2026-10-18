# SPDX-License-Identifier: MIT

import json
from pathlib import Path
from harbourmaster.i18n import _
from loguru import logger
from . import config as hm_config
from .config import HM_SORT_ORDER
from .util import PORT_SORT_FUNCS, add_dict_list_unique, add_list_unique, add_pm_signature, get_dict_list, hash_file, load_pm_signature, match_requirements, name_cleaner, oc_join, remove_dict_list, timeit, version_parse
from .info import port_info_load, port_info_merge


class PortsMixin:
    """
    HarbourMaster methods: Installed and available ports: scanning the ports dir, filtering, listing and port info.
    """


    def _get_pm_signature(self, file_name):
        """
        Returns (file_name, original_file_name, port_name)

        This handles files being renamed, hopefully.
        """
        if not str(file_name).lower().endswith('.sh'):
            return None

        # See if the file has a signature
        pm_signature = load_pm_signature(file_name)

        if pm_signature is None:
            ports_info = self.ports_info()

            # If not look it up by name
            port_owners = get_dict_list(ports_info['items'], file_name.name)
            if len(port_owners) > 0:
                add_pm_signature(file_name, [port_owners[0], file_name.name])
                return (file_name.name, file_name.name, port_owners[0])

            # Finally try by the md5sum of the file
            md5 = hash_file(file_name)
            if md5 in ports_info['md5']:
                other_name = ports_info['md5'][md5]

                port_owners = get_dict_list(ports_info['items'], other_name)

                if len(port_owners) > 0:
                    add_pm_signature(file_name, [port_owners[0], other_name])
                    return (other_name, file_name.name, port_owners[0])

            return (file_name.name, file_name.name, None)

        return (file_name.name, pm_signature[1], pm_signature[0])

    def _load_port_info(self, port_file):
        """
        Loads a <blah>.port.json file.

        It will try its best to recover the data into a usable state.

        returns None if it is unusuable.
        """
        port_info = port_info_load(port_file, do_default=True)

        ports_info = self.ports_info()
        changed = False

        # Its possible for the port_info to be in a bad way, lets try and fix it.
        if port_info.get('name', None) is None:
            # No name, check the items and see if it matches our internal database, we can get the port name from a script.
            logger.error(f"No 'name' in {port_file!r}")
            if port_info.get('items', None) is None:
                # Can't do shit if the items is empty. :(
                logger.error(f"Unable to load {port_file}, missing 'name' and 'items' keys.")
                return None

            for item in port_info['items']:
                port_temp = ports_info['items'].get(item.casefold(), None)
                if isinstance(port_temp, str):
                    break
            else:
                # Couldn't find the port.
                logger.error(f"Unable to load {port_file}, unknown items.")
                return None

            changed = True
            port_info['name'] = name_cleaner(port_temp[0])

        # Force the port_info['name'] to be lowercase/casefolded.
        if port_info['name'] != name_cleaner(port_info['name']):
            port_info['name'] = name_cleaner(port_info['name'])
            changed = True

        if port_info.get('items', None) is None:
            # This shouldn't happen, but we can restore it.
            logger.error(f"No 'items' in {port_info!r} for {port_file}")

            if port_info['name'] not in ports_info['ports']:
                # Sorry, cant work it out.
                logger.error(f"Unable to figure it out, unknown port {port_info['name']}")
                return None

            changed = True
            port_info['items'] = ports_info['ports'][port_info['name']]['items'][:]

        if port_info['attr']['title'] in ("", None):
            for item in port_info['items']:
                if item.casefold().endswith('.sh'):
                    port_info['attr']['title'] = item[:-3]
                    changed = True
                    break

        if port_info.get('status', None) is None:
            changed = True
            port_info['status'] = {
                'source': 'Unknown',
                'md5': None,
                'status': 'Unknown',
                }

        if port_info.get('source', None) is not None:
            changed = True
            del port_info['source']

        port_info['changed'] = changed

        return port_info

    def _iter_ports_dir(self):
        if self.ports_dir != self.scripts_dir:
            yield from self.scripts_dir.iterdir()

        yield from self.ports_dir.iterdir()

    def _ports_dir_exists(self, file_name):
        if (self.scripts_dir / file_name).exists():
            return True

        return (self.ports_dir / file_name).exists()

    def _ports_dir_is_file(self, file_name):
        if (self.scripts_dir / file_name).is_file():
            return True

        return (self.ports_dir / file_name).is_file()

    def _ports_dir_is_dir(self, file_name):
        if (self.scripts_dir / file_name).is_dir():
            return True

        return (self.ports_dir / file_name).is_dir()

    def _ports_dir_relative_to(self, path):
        try:
            return path.relative_to(self.scripts_dir)

        except ValueError:
            return path.relative_to(self.ports_dir)

    def _ports_dir_file(self, file_name, is_script=False):
        if is_script:
            return (self.scripts_dir / file_name)

        return (self.ports_dir / file_name)

    @timeit
    def load_ports(self):
        """
        Find all installed ports, because ports can be installed by zips we need to recheck every time.
        """
        port_files = list(self.ports_dir.glob('*/*.port.json')) + list(self.ports_dir.glob('*/port.json'))
        port_files.sort()

        self.installed_ports = {}
        self.broken_ports = {}
        self.unknown_ports = []
        all_items = {}
        unknown_files = []

        all_ports = {}
        ports_files = {}
        file_renames = {}

        ports_info = self.ports_info()
        self._PORT_INFO_CACHE.clear()

        self.callback.message("  - {}".format(_("Loading Ports.")))

        """
        This is a bit of a heavy function but it does the following.

        Phase 1:
        - Load all *.port.json files, fix any issues with them
    
        Phase 2:
        - Check all files/dirs in the ports_dir, see if they are "owned" by a port, find any renamed files.

        Phase 3:
        - Find any new ports, create the port.json files as necessary.

        Phase 4:
        - Finalise any data, figure out if the ports are broken etc.

        DONE.

        """

        ## Rename old <portname>.port.json to port.json.
        port_dirs = {}

        for port_file in port_files:
            port_dir = port_file.parent.name

            port_dirs.setdefault(port_dir, {})[port_file.name] = port_file

        changes = False
        for port_dir in port_dirs:
            if port_dir == 'alephone':
                continue

            # Rename the port.json
            port_jsons = list(port_dirs[port_dir].keys())

            if len(port_jsons) == 1:
                if 'port.json' not in port_jsons:
                    port_dir_path = port_dirs[port_dir][port_jsons[0]].parent

                    ## Rename
                    logger.debug(f"rename {port_dir_path / port_jsons[0]} to {port_dir_path / 'port.json'}")
                    (port_dir_path / port_jsons[0]).rename(port_dir_path / 'port.json')
                    changes = True

            elif len(port_jsons) == 2:
                if 'port.json' not in port_jsons:
                    ## HRMMmmmmm
                    logger.debug(f'Multiple port.json files in {port_dir}: {port_jsons}')
                    continue

                else:
                    # Remove the old one.
                    port_jsons.remove('port.json')
                    port_dir_path = port_dirs[port_dir][port_jsons[0]].parent
                    logger.debug(f"unlink {port_dir_path / port_jsons[0]}")
                    (port_dir_path / port_jsons[0]).unlink()
                    changes = True

            else:
                if 'port.json' not in port_jsons:
                    ## HRMMmmmmm
                    logger.debug(f'Multiple port.json files in {port_dir}: {port_jsons}')
                    continue

        del port_dirs

        if changes:
            # Reload the port_files list.
            port_files = list(self.ports_dir.glob('*/*.port.json')) + list(self.ports_dir.glob('*/port.json'))


        ## Phase 1: Load all the known ports with port.json files
        for port_file in port_files:
            try:
                port_info = self._load_port_info(port_file)
            except Exception as err:
                logger.error(f"[HarbourMaster] Failed to load metadata from '{port_file}': {err}")
                continue

            if not port_info:
                logger.warning(f"[HarbourMaster] Skipping invalid port file '{port_file}'")
                continue
            # The files attribute keeps track of file renames.
            if port_info.get('files', None) is None:
                port_info['files'] = {
                    'port.json': str(self._ports_dir_relative_to(port_file)),
                    }
                port_info['changed'] = True

            if 'port.json' not in port_info['files']:
                port_info['files']['port.json'] = str(self._ports_dir_relative_to(port_file))
                port_info['changed'] = True

            if port_info['attr']['porter'] is None:
                port_info['attr']['porter'] = ['Unknown']
                port_info['changed'] = True

            if isinstance(port_info['attr']['porter'], str):
                port_info['attr']['porter'] = ports_info['portsmd_fix'].get(port_info['attr']['porter'].lower(), port_info['attr']['porter'])
                port_info['changed'] = True

            # Add all the root dirs/scripts in the port
            for item in port_info['items']:
                add_dict_list_unique(all_items, item, port_info['name'])

                if self._ports_dir_exists(item):
                    if item not in get_dict_list(port_info['files'], item):
                        add_dict_list_unique(port_info['files'], item, item)
                        port_info['changed'] = True

            # And any optional ones.
            for item in get_dict_list(port_info, 'items_opt'):
                add_dict_list_unique(all_items, item, port_info['name'])

                if self._ports_dir_exists(item):
                    if item not in get_dict_list(port_info['files'], item):
                        add_dict_list_unique(port_info['files'], item, item)
                        port_info['changed'] = True

            all_ports[port_info['name']] = port_info
            ports_files[port_info['name']] = port_file

        ## Phase 2: Check all files
        for file_item in self._iter_ports_dir():
            ## Skip these
            if file_item.name.lower() in (
                    'gamelist.xml',
                    'gamelist.xml.old',
                    'harbourmaster',
                    'images',
                    'manuals',
                    'portmaster',
                    'portmaster.sh',
                    'thememaster',
                    'thememaster.sh',
                    'videos',
                    ):
                continue

            file_name = file_item.name
            if file_item.is_dir():
                file_name += '/'

            elif file_item.suffix.casefold() not in ('.sh', ):
                # Ignore non bash files.
                continue

            if file_item.is_file():
                with open(file_item, 'rb') as fh:
                    file_header = fh.read(1024)
                    if b"PORTMASTER NO TOUCHY" in file_header:
                        logger.debug(f"NO TOUCHY {file_name}")
                        continue

            port_owners = get_dict_list(all_items, file_name)

            if len(port_owners) > 0:
                # We know what port this file belongs to.
                # Add signature to files
                if file_item.suffix.casefold() in ('.sh', ):
                    pm_signature = load_pm_signature(file_item)

                    if pm_signature is None:
                        logger.debug(f"add_pm_signature({file_item!r}, [{port_owners[0]!r}, {file_name!r}])")
                        add_pm_signature(file_item, [port_owners[0], file_name])
                        continue

                    if pm_signature[0] in all_ports:
                        port_info = all_ports[pm_signature[0]]
                        # print(file_name, pm_signature)
                        if file_name not in get_dict_list(port_info['files'], pm_signature[1]):
                            add_dict_list_unique(port_info['files'], pm_signature[1], file_name)
                            print("added")
                            port_info["changed"] = True

                continue

            if not file_name.endswith('/'):
                # See if the file has been renamed, thanks Christian!
                pm_signature = self._get_pm_signature(file_item)
                if pm_signature is None:
                    # Shouldn't happen
                    unknown_files.append(file_name)
                    continue

                if pm_signature[0] != pm_signature[1]:
                    # We atleast know the file is renamed.
                    file_renames[pm_signature[1]] = pm_signature[0]

                if pm_signature[2] is None:
                    # Unknown port?
                    unknown_files.append(file_name)
                    continue

                if pm_signature[2] in all_ports:
                    port_info = all_ports[pm_signature[2]]
                    add_dict_list_unique(all_items, pm_signature[0], pm_signature[2])

                    if pm_signature[0] not in get_dict_list(port_info['files'], pm_signature[1]):
                        add_dict_list_unique(port_info['files'], pm_signature[1], pm_signature[0])
                        port_info["changed"] = True

                    continue

            unknown_files.append(file_name)

        # from pprint import pprint
        # pprint(all_items)
        # pprint(file_renames)
        # pprint(unknown_files)

        ## Create new ports.
        new_ports = []
        for unknown_file in unknown_files:
            port_owners = get_dict_list(ports_info['items'], unknown_file)

            if len(port_owners) == 1:
                add_list_unique(new_ports, port_owners[0])

            elif len(port_owners) == 0:
                if unknown_file.casefold().endswith('.sh'):
                    re_name = file_renames.get(unknown_file, None)
                    if re_name is not None:
                        port_owners = get_dict_list(ports_info['items'], re_name)

                        if len(port_owners) == 1:
                            if port_owners[0] in all_ports:
                                port_info = all_ports[port_owners[0]]
                                if unknown_file not in get_dict_list(port_info['files'], re_name):
                                    add_dict_list_unique(port_info['files'], re_name, unknown_file)
                                    port_info['changed'] = True

                            else:
                                add_list_unique(new_ports, port_owners[0])

                            continue

                    ## Keep track of unknown bash scripts.
                    logger.info(f"Unknown port: {unknown_file}")
                    self.unknown_ports.append(unknown_file)

        ## Create new port.json files for any new ports, these only contain the most basic of information.
        for new_port in new_ports:
            port_info_raw = ports_info['ports'][new_port]

            port_info = port_info_load(port_info_raw)

            port_file = self._ports_dir_file(port_info_raw['file'])

            ## Load extra info
            for source in self.sources.values():
                port_name = source.clean_name(port_info['name'])

                if port_name in source.ports:
                    port_info_merge(port_info, source.port_info(port_name))
                    break

            if port_info['attr']['title'] in ("", None):
                for item in port_info['items']:
                    if item.casefold().endswith('.sh'):
                        port_info['attr']['title'] = item[:-3]
                        break

            if port_info['attr']['porter'] is None:
                port_info['attr']['porter'] = ['Unknown']

            if isinstance(port_info['attr']['porter'], str):
                port_info['attr']['porter'] = ports_info['portsmd_fix'].get(
                    port_info['attr']['porter'].lower(),
                    port_info['attr']['porter'])

            if port_info.get('status', None) is None:
                port_info['status'] = {}

            port_info['name'] = port_info['name'].casefold()

            port_info['status']['source'] = "Unknown"
            port_info['status']['md5'] = None
            port_info['status']['status'] = "Unknown"

            port_info['files'] = {
                'port.json': port_info_raw['file'],
                }

            # Add all the root dirs/scripts in the port
            for item in port_info['items']:
                if self._ports_dir_exists(item):
                    if item not in get_dict_list(port_info['files'], item):
                        add_dict_list_unique(port_info['files'], item, item)
                        port_info['changed'] = True

                if item in file_renames:
                    item_rename = file_renames[item]
                    if self._ports_dir_exists(item_rename):
                        if item_rename not in get_dict_list(port_info['files'], item):
                            add_dict_list_unique(port_info['files'], item, item_rename)
                            port_info['changed'] = True

            # And any optional ones.
            for item in get_dict_list(port_info, 'items_opt'):
                if self._ports_dir_exists(item):
                    if item not in get_dict_list(port_info['files'], item):
                        add_dict_list_unique(port_info['files'], item, item)
                        port_info['changed'] = True

                if item in file_renames:
                    item_rename = file_renames[item]
                    if self._ports_dir_exists(item_rename):
                        if item_rename not in get_dict_list(port_info['files'], item):
                            add_dict_list_unique(port_info['files'], item, item_rename)
                            port_info['changed'] = True

            port_info['changed'] = True

            all_ports[port_info['name']] = port_info
            ports_files[port_info['name']] = port_file

        for port_name in all_ports:
            port_info = all_ports[port_name]

            bad = False
            for port_file in list(port_info['files']):
                file_names = get_dict_list(port_info['files'], port_file)

                for file_name in list(file_names):
                    if not self._ports_dir_exists(file_name):
                        remove_dict_list(port_info['files'], port_file, file_name)
                        port_info['changed'] = True

            for item in port_info['items']:
                if len(get_dict_list(port_info['files'], item)) == 0:
                    logger.error(f"Port {port_name} missing {item}.")
                    bad = True

            if bad:
                if port_info['status'].get('status', 'Unknown') != 'Broken':
                    port_info['status']['status'] = 'Broken'
                    port_info['changed'] = True

                self.broken_ports[port_name] = port_info

            else:
                if port_info['status'].get('status', 'Unknown') != 'Installed':
                    port_info['status']['status'] = 'Installed'
                    port_info['changed'] = True

                self.installed_ports[port_name] = port_info

            changed = port_info['changed']
            del port_info['changed']

            if 'source' in port_info:
                del port_info['source']
                changed = True

            if changed:
                if ports_files[port_name].parent.is_dir():
                    logger.debug(f"Dumping {str(ports_files[port_name])}: {port_info}")
                    with ports_files[port_name].open('wt') as fh:
                        json.dump(port_info, fh, indent=4)
                else:
                    logger.warning(f"Unable to dump {str(ports_files[port_name])}: {port_info}")

    def port_info_attrs(self, port_info):
        runtime_fix = {
            'godot': 'godot',
            'frt':  'godot',
            'mono': 'mono',
            'rlvm': 'rlvm',
            'solarus': 'solarus',
            'jdk11': 'jre',
            'jre': 'jre',
            'weston': 'weston',
            'mesa': 'mesa',
            }

        attrs = []
        runtimes = port_info.get('attr', {}).get('runtime', [])
        if len(runtimes) > 0:
            if isinstance(runtimes, str):
                runtimes = [runtimes]

            for runtime_key, runtime_attr in runtime_fix.items():
                for runtime in runtimes:
                    if runtime_key in runtime:
                        add_list_unique(attrs, runtime_attr)

        for genre in port_info.get('attr', {}).get('genres', []):
            add_list_unique(attrs, genre.casefold())

        for porter in port_info.get('attr', {}).get('porter', []):
            add_list_unique(attrs, porter.casefold())

        rtr = port_info.get('attr', {}).get('rtr', False)
        if rtr:
            add_list_unique(attrs, 'rtr')
        else:
            add_list_unique(attrs, '!rtr')

        exp = port_info.get('attr', {}).get('exp', False)
        if exp:
            add_list_unique(attrs, 'exp')

        if port_info['name'].casefold() in self.installed_ports:
            add_list_unique(attrs, 'installed')

        if port_info['name'].casefold() in self.broken_ports:
            add_list_unique(attrs, 'installed')
            add_list_unique(attrs, 'broken')

        if 'source' in port_info and 'status' in port_info:
            source_md5 = port_info['source'].get('md5', None)
            status_md5 = port_info['status'].get('md5', None)
            if status_md5 is not None and source_md5 != status_md5:
                add_list_unique(attrs, 'update available')

        # print(f"{port_info['name']}: {exp!r} {attrs}")

        return attrs

    def match_filters(self, port_filters, port_info):
        port_attrs = self.port_info_attrs(port_info)

        if not self.cfg_data['show_experimental'] and 'exp' in port_attrs:
            return False

        for port_filter in port_filters:
            if port_filter.casefold() not in port_attrs:
                return False

        return True

    def match_requirements(self, port_info):
        """
        Matches hardware capabilities to port requirements.
        """
        if not hasattr(self, '_TESTING'):
            self._TESTING = {}

        show = False
        capabilities = self.device['capabilities']

        requirements = port_info.get('attr', {}).get('reqs', [])
        if requirements is not None:
            requirements = requirements[:]
        else:
            requirements = []

        runtimes = port_info.get('attr', {}).get('runtime', [])

        min_glibc = port_info.get('attr', {}).get('min_glibc', "")

        if min_glibc not in ("", None) and isinstance(min_glibc, str):
            if version_parse(min_glibc.strip()) > version_parse(self.device['glibc']):
                return False

        if len(runtimes) > 0:
            for runtime in runtimes:
                if not runtime.endswith('.squashfs'):
                    runtime += '.squashfs'

                requirements.append('|'.join(self.runtimes_info.get(runtime, {}).get('remote', {}).keys()))
                show = True

        else:
            arch = port_info.get('attr', {}).get('arch', [])

            if isinstance(arch, list) and len(arch) > 0:
                requirements.append('|'.join(arch))

        if self.cfg_data.get('show_all', False):
            requirements = []

        result = match_requirements(capabilities, requirements)
        if hm_config.HM_DEBUG and port_info['name'] not in self._TESTING:
            if show:
                print(f"{port_info['name']}: {capabilities}, {requirements}: {result}")
            self._TESTING[port_info['name']] = True

        return result

    def build_port_attrs(self):
        """
        With this function we create a cache of source_port_attrs and installed_port_attrs.

        These are a dict of each port attr, and a set of ports that match those attrs.

        Instead of manually refreshing this info every time we filter the ports list we
        can just do simple intersection of the current filters and it will give us the
        availble list of ports.

        As installed ports will have different filter set from source ports,
        we keep them as a separate dict.

        If something changes in the installed ports or ports available,
        assign `self._port_attrs_updated` to True and this will cause a refresh.
        """
        self._source_port_attrs = {}
        self._installed_port_attrs = {}
        self._all_ports_set = set()

        self._port_attrs_updated = False

        installed_ports = set()

        all_attrs = set()

        for port_name in self.installed_ports:
            port_name = name_cleaner(port_name)

            new_port_info = self.port_info(port_name, installed=True)

            new_port_attrs = self.port_info_attrs(new_port_info)

            self._all_ports_set.add(port_name)
            installed_ports.add(port_name)

            for port_attr in new_port_attrs:
                all_attrs.add(port_attr)
                self._installed_port_attrs.setdefault(port_attr, set()).add(port_name)

        for port_name, port_info in self.broken_ports.items():
            port_name = name_cleaner(port_name)

            if port_name in installed_ports:
                continue

            self._all_ports_set.add(port_name)

            new_port_info = self.port_info(port_name, installed=True)

            new_port_attrs = self.port_info_attrs(new_port_info)

            installed_ports.add(port_name)

            for port_attr in new_port_attrs:
                all_attrs.add(port_attr)
                self._installed_port_attrs.setdefault(port_attr, set()).add(port_name)

        for source_prefix, source in self.sources.items():
            for port_name in source.ports:
                port_name = name_cleaner(port_name)

                new_port_info = self.port_info(port_name, installed=False)

                if not self.match_requirements(new_port_info):
                    logger.debug(f"skip incompatible port {port_name}.")
                    continue

                new_port_attrs = self.port_info_attrs(new_port_info)

                # Skip experimental ports if they are not enabled.
                if not self.cfg_data.get('show_experimental', False) and 'exp' in new_port_attrs:
                    if not self.cfg_data.get('show_all', False):
                        logger.debug(f"skip experimental port {port_name}.")
                        continue

                # This needs be done after all the fucking filtering. -- Happy Jan?
                self._all_ports_set.add(port_name)

                for port_attr in new_port_attrs:
                    all_attrs.add(port_attr)
                    self._source_port_attrs.setdefault(port_attr, set()).add(port_name)

                    if port_name not in installed_ports:
                        self._installed_port_attrs.setdefault(port_attr, set()).add(port_name)

    def list_ports(self, filters=[], sort_by='alphabetical', reverse=False):
        """
        This is deprecated, and overall a really bad idea.
        """

        ## Filters can be genre, runtime
        if sort_by not in HM_SORT_ORDER:
            sort_by = HM_SORT_ORDER[0]

        sort_by_reverse_order = ('recently_added', 'recently_updated')
        if sort_by in sort_by_reverse_order:
            reverse = not reverse

        tmp_ports = {}
        not_installed = 'not installed' in filters
        if not_installed:
            filters = list(filters)
            filters.remove('not installed')

        if not not_installed and 'installed' in filters:
            for port_name in self.installed_ports:
                if name_cleaner(port_name) in tmp_ports:
                    continue

                new_port_info = self.port_info(port_name, installed=True)

                if not self.match_filters(filters, new_port_info):
                    continue

                tmp_ports[name_cleaner(port_name)] = new_port_info

            for port_name, port_info in self.broken_ports.items():
                if name_cleaner(port_name) in tmp_ports:
                    continue

                new_port_info = self.port_info(port_name, installed=True)

                if not self.match_filters(filters, new_port_info):
                    continue

                tmp_ports[name_cleaner(port_name)] = new_port_info

        for source_prefix, source in self.sources.items():
            for port_name in source.ports:
                if not_installed and (
                        name_cleaner(port_name) in self.installed_ports.keys() or
                        name_cleaner(port_name) in self.broken_ports.keys()):
                    continue

                if name_cleaner(port_name) in tmp_ports:
                    # print(f"- {port_name} skipping (1)")
                    continue

                new_port_info = self.port_info(port_name, installed=False)

                if not self.match_filters(filters, new_port_info):
                    # print(f"- {port_name} skipping (2)")
                    continue

                if not self.match_requirements(new_port_info):
                    # print(f"- {port_name} skipping (3)")
                    continue

                tmp_ports[name_cleaner(port_name)] = new_port_info

        ports = {
            port_name: port_info
            for port_name, port_info in sorted(
                tmp_ports.items(),
                key=lambda x: (PORT_SORT_FUNCS[sort_by](x[1]), x[0].casefold()),
                reverse=reverse)
            }

        return ports

    def list_ports_names_new(self, filters=[], sort_by='alphabetical', reverse=False):

        ## Filters can be genre, runtime
        if sort_by not in HM_SORT_ORDER:
            sort_by = HM_SORT_ORDER[0]

        ## Rebuild the port attribute sets.
        if self._port_attrs_updated:
            self.build_port_attrs()

        tmp_ports = self._all_ports_set.copy()

        not_installed = 'not installed' in filters
        if not_installed:
            filters = list(filters)
            filters.remove('not installed')

            if 'installed' not in filters:
                tmp_ports.difference_update(self._source_port_attrs.get('installed', set()))
                tmp_ports.difference_update(self._installed_port_attrs.get('installed', set()))
            else:
                # sigh...
                tmp_ports = set()

        if 'installed' in filters:
            for filter_attr in filters:
                tmp_ports.intersection_update(self._installed_port_attrs.get(filter_attr.casefold(), set()))

        else:
            for filter_attr in filters:
                tmp_ports.intersection_update(self._source_port_attrs.get(filter_attr.casefold(), set()))

        return list(tmp_ports)

    def list_ports_new(self, filters=[], sort_by='alphabetical', reverse=False):

        tmp_ports = self.list_ports_names_new(filters, sort_by, reverse)

        ports_list = {}

        installed_status = 'installed' in filters

        sort_by_reverse_order = ('recently_added', 'recently_updated', 'total_downloads')
        if sort_by in sort_by_reverse_order:
            reverse = not reverse

        for port_name in tmp_ports:
            port_info = self.port_info(port_name, installed=installed_status)

            if port_info is None:
                port_info = self.port_info(port_name, installed=False)

            if port_info is None:
                port_info = self.port_info(port_name, installed=True)

            # if port_info is None:
            #     continue

            ports_list[port_name] = port_info            

        ports = {
            port_name: port_info
            for port_name, port_info in sorted(
                ports_list.items(),
                key=lambda x: (PORT_SORT_FUNCS[sort_by](x[1]), x[0].casefold()),
                reverse=reverse)
            }

        return ports

    def list_utils(self):

        utils = []

        for source_prefix, source in self.sources.items():
            for util_name in source.utils:
                if util_name in utils:
                    continue

                utils.append(util_name)

        return utils

    def port_images(self, port_name):
        for source_prefix, source in self.sources.items():
            if name_cleaner(port_name) in getattr(source, 'images', {}):
                return {
                    image_type: (source._images_dir / image_file)
                    for image_type, image_file in source.images[name_cleaner(port_name)].items()}

        return self._installed_port_images(port_name)

    def _installed_port_images(self, port_name):
        """
        The screenshot shipped inside an installed port, for ports no source has
        images for (eg: testing ports). Port zips carry <port dir>/screenshot.png,
        but their own port.json usually leaves "image" empty.
        """
        port_info = self.installed_ports.get(name_cleaner(port_name))
        if port_info is None:
            return None

        port_json = port_info.get('files', {}).get('port.json')
        if not isinstance(port_json, str):
            return None

        port_dir = self._ports_dir_file(port_json).parent

        candidates = []
        image = port_info.get('attr', {}).get('image', {})
        if isinstance(image, dict) and isinstance(image.get('screenshot'), str):
            candidates.append(image['screenshot'])

        candidates += ['screenshot.png', 'screenshot.jpg']

        for candidate in candidates:
            candidate_path = Path(candidate)

            ## Stay inside the port's own directory.
            if candidate_path.is_absolute() or '..' in candidate_path.parts:
                continue

            if (port_dir / candidate_path).is_file():
                return {'screenshot': port_dir / candidate_path}

        return None

    def port_info(self, port_name, installed=False):
        result = None

        port_key = (name_cleaner(port_name), installed)
        if port_key in self._PORT_INFO_CACHE:
            return self._PORT_INFO_CACHE[port_key]

        if installed:
            if port_name in self.installed_ports:
                result = port_info_load(self.installed_ports[name_cleaner(port_name)])

            elif port_name in self.broken_ports:
                result = port_info_load(self.broken_ports[name_cleaner(port_name)])

        for source_prefix, source in self.sources.items():
            if source.clean_name(port_name) in source.ports:
                if result is not None:
                    port_info_merge(result, source.port_info(port_name))

                else:
                    result = port_info_load(source.port_info(port_name))

        if result is None:
            self._PORT_INFO_CACHE[port_key] = result
            return None

        if not installed:
            if port_name in self.installed_ports:
                 port_info_merge(result, self.installed_ports[name_cleaner(port_name)])

            elif port_name in self.broken_ports:
                 port_info_merge(result, self.broken_ports[name_cleaner(port_name)])

        if 'source' in result:
            result['source']['downloads'] = self.port_downloads(port_name)

        self._PORT_INFO_CACHE[port_key] = result
        return result

    def port_download_size(self, port_name, check_runtime=True):
        for source_prefix, source in self.sources.items():
            clean_name = source.clean_name(port_name)
            if clean_name not in source.ports:
                if clean_name not in source.utils:
                    continue

            return source.port_download_size(port_name, check_runtime)

        return 0

    def port_download_url(self, port_name):
        for source_prefix, source in self.sources.items():
            clean_name = source.clean_name(port_name)
            if clean_name not in source.ports:
                if clean_name not in source.utils:
                    continue

            return source.port_download_url(port_name)

        return None

    def portmd(self, port_info):
        def nice_value(value):
            if value is None:
                return ""
            if value == "None":
                return ""
            return value

        output = []

        if 'opengl' in port_info["attr"]["reqs"]:
            output.append(f'<r>Title_F</r>="<y>{port_info["attr"]["title"].replace(" ", "_")} .</y>"')
        elif 'power' in port_info["attr"]['reqs']:
            output.append(f'<r>Title_P</r>="<y>{port_info["attr"]["title"].replace(" ", "_")} .</y>"')
        else:
            output.append(f'<r>Title</r>="<y>{port_info["attr"]["title"].replace(" ", "_")} .</y>"')

        output.append(f'<r>Desc</r>="<y>{nice_value(port_info["attr"]["desc"])}</y>"')
        output.append(f'<r>porter</r>="<y>{oc_join(port_info["attr"]["porter"])}</y>"')
        output.append(f'<r>locat</r>="<y>{nice_value(port_info["name"])}</y>"')
        if port_info["attr"]['rtr']:
            output.append(f'<r>runtype</r>="<e>rtr</e>"')
        if port_info["attr"]['runtime'] == "mono-6.12.0.122-aarch64.squashfs":
            output.append(f'<r>mono</r>="<e>y</e>"')

        output.append(f'<r>genres</r>="<m>{",".join(port_info["attr"]["genres"])}</m>"')

        return ' '.join(output)
