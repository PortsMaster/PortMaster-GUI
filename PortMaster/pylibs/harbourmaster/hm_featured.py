# SPDX-License-Identifier: MIT

from loguru import logger
from .util import json_safe_load


class FeaturedMixin:
    """
    HarbourMaster methods: Featured ports lists.
    """

    def featured_ports(self, pre_load=False):
        featured_ports_file = self.cfg_dir / "featured_ports.json"
        featured_ports_dir = self.cfg_dir / "featured_ports/"

        if not featured_ports_dir.is_dir():
            featured_ports_dir.mkdir(0o755)

        if not featured_ports_file.is_file():
            return []

        with featured_ports_file.open('r') as fh:
            featured_ports = json_safe_load(fh)

        if not isinstance(featured_ports, list):
            return []

        return self._process_featured_ports_items(featured_ports, featured_ports_dir, pre_load)

    def _process_featured_ports_items(self, items, featured_ports_dir, pre_load, path_prefix=""):
        results = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            if item.get('name', None) in (None, ""):
                if pre_load:
                    logger.error(f"Bad featured_ports{path_prefix}[{idx}]: Missing name")
                continue

            item_type = item.get('type', 'ports')  # Default to 'ports' for backward compatibility

            # Handle nested categories
            if item_type == 'category':
                children = item.get('children', [])
                if not isinstance(children, list):
                    if pre_load:
                        logger.error(f"Bad featured_ports{path_prefix}[{idx}]: category children must be a list")
                    continue

                processed_item = {
                    'name': item['name'],
                    'description': item.get('description', ''),
                    'image': self._process_featured_ports_image(item.get('image'), featured_ports_dir),
                    'type': 'category',
                    'children': self._process_featured_ports_items(children, featured_ports_dir, pre_load, f"{path_prefix}[{idx}].children")
                    }

                # Only include categories that have children
                if len(processed_item['children']) > 0:
                    results.append(processed_item)

            else:  # item_type == 'ports' or backward compatibility
                # Is this an older deprecated featured ports list?
                deprecated_list = item.get('deprecated', False)
                if deprecated_list:
                    continue

                # Handle port lists (backward compatible with old format)
                ports_list = item.get('ports', None)
                if ports_list is None:
                    if pre_load:
                        logger.error(f"Bad featured_ports{path_prefix}[{idx}]: Missing ports info")
                    continue

                if not isinstance(ports_list, list):
                    if pre_load:
                        logger.error(f"Bad featured_ports{path_prefix}[{idx}]: bad ports item")
                    continue

                port_list_ports = {}
                for idx2, port_name in enumerate(ports_list):
                    port_info = self.port_info(port_name)
                    if port_info is None:
                        if pre_load:
                            logger.error(f"Bad featured_ports{path_prefix}[{idx}]['ports'][{idx2}]: unknown port {port_name}")
                        continue

                    # Only show ports in here that are possible to install.
                    if not self.match_requirements(port_info):
                        continue

                    port_list_ports[port_info['name']] = port_info

                if len(port_list_ports) == 0:
                    # Don't show empty featured ports.
                    continue

                processed_item = {
                    'name': item['name'],
                    'description': item.get('description', ''),
                    'image': self._process_featured_ports_image(item.get('image'), featured_ports_dir),
                    'type': 'ports',
                    'ports': port_list_ports,
                }

                results.append(processed_item)

        return results

    def _process_featured_ports_image(self, image_name, featured_ports_dir):
        if image_name is not None and image_name != "":
            # image_url = self.PORT_INFO_URL + image_name
            image_file = featured_ports_dir / image_name.rsplit('/', 1)[-1]

            if not image_file.is_file():
                ## We no longer download here, it is now done in load_info.
                # download_info = download(image_file, image_url, callback=self.callback, no_check=True)
                # if download_info is None:
                return ""

            return str(image_file)
        return ""
