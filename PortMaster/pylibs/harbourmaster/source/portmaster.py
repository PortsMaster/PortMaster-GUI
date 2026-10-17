# SPDX-License-Identifier: MIT
#
# PortMasterV3, the PortMaster sources: ports.json and port images from a GitHub release.

import datetime
import json
import zipfile
from gettext import gettext as _
from loguru import logger
from ..config import HM_MAX_TEMP_SIZE
from ..info import port_info_load, port_info_merge
from ..util import json_safe_load
from ..util import net
from .base import BaseSource


class PortMasterV3(BaseSource):
    """
    The PortMaster sources: a ports.json release asset listing every port and util
    (runtimes, images.zip, images.NNN.zip, gameinfo.zip), cached in the source file.
    """
    VERSION = 2

    # A safe number, at this point its better to just download the full zip again.
    MAX_IMAGES_XXX_ZIP = 4

    ## Loading and saving
    def load(self):
        self._data = self._config.setdefault('data', {}).setdefault('data', {})
        self.ports = self._config.setdefault('data', {}).setdefault('ports', [])
        self.utils = self._config.setdefault('data', {}).setdefault('utils', [])
        self._info = self._config.setdefault('data', {}).setdefault('info', {})
        self._load_images()

    def save(self):
        with self._file_name.open('w') as fh:
            json.dump(self._config, fh, indent=4)

    ## Updating from ports.json
    def update(self):
        if self.hm.callback is not None:
            self.hm.callback.message(" - {}".format(_("Updating")))

        changed = False
        # Scrap the rest
        self._data = {}
        self._info = {}
        self.ports = []
        self.utils = []
        self.images = {}

        if self._did_update:
            self.hm.callback.message(" - {}".format(_("Up to date already")))
            return

        if self.hm.callback is not None:
            self.hm.callback.message("  - {}".format(_("Fetching latest info")))

        data = net.fetch_json(self._config['url'])
        if data is None:
            return

        ## Load data from the assets.
        for key, asset in data['ports'].items():
            asset = port_info_load(asset)
            if asset is None:
                ## Skip bad items.
                continue

            result = {
                'name': asset['name'],
                'size': asset['source']['size'],
                'md5': asset['source']['md5'],
                'url': asset['source']['url'],
                }

            self.ports.append(self.clean_name(key))
            self._info[self.clean_name(key)] = asset
            self._data[self.clean_name(key)] = result

        for key, asset in data['utils'].items():
            result = {
                'name': asset['name'],
                'size': asset['size'],
                'md5': asset['md5'],
                'url': asset['url'],
                }

            if 'images' in asset:
                result['images'] = asset['images']

            if key.endswith('.squashfs'):
                if 'runtime_name' in asset:
                    key=asset['runtime_name']
                    arch=asset['runtime_arch']
                    self.hm.runtimes_info.setdefault(key, {}).setdefault('remote', {})[arch] = result.copy()

                else:
                    self.hm.runtimes_info.setdefault(key, {}).setdefault('remote', {})['aarch64'] = result.copy()

                if 'name' in self.hm.runtimes_info[key]['remote']:
                    del self.hm.runtimes_info[key]['remote']['name']
                    del self.hm.runtimes_info[key]['remote']['size']
                    del self.hm.runtimes_info[key]['remote']['md5']
                    del self.hm.runtimes_info[key]['remote']['url']

                self.hm.runtimes_info[key]['name'] = result['name']
                self.hm.runtimes_info[key].setdefault('status', 'Unknown')
                changed = True

            self._data[self.clean_name(key)] = result
            if key.lower() in ('images.zip', 'portmaster.zip'):
                continue

            self.utils.append(self.clean_name(key))

        if changed:
            self.hm.list_runtimes()
            self.hm.save_config()

        self._update_images()

        self._load_images()

        self._config['version'] = self.VERSION

        self._config['data']['ports'] = self.ports
        self._config['data']['utils'] = self.utils
        self._config['data']['data']  = self._data
        self._config['data']['info']  = self._info

        self._config['last_checked'] = datetime.datetime.now().isoformat()

        self.save()
        self._did_update = True
        self.hm.callback.message("  - {}".format(_("Done.")))

    ## Port images
    def _load_images(self):
        self.images = {}
        all_ports = set(self.ports)
        seen_ports = set()

        for file_name in self._images_dir.iterdir():
            if file_name.suffix.casefold() not in ('.jpg', '.png'):
                continue

            if file_name.name.count('.') < 2:
                continue

            port_name, image_type, image_suffix = file_name.name.casefold().rsplit('.', 2)
            port_name = self.clean_name(port_name + '.zip')

            if port_name not in all_ports:
                logger.warning(f"Port image {port_name} - {image_type} for unknown port.")
            elif image_type == 'screenshot':
                seen_ports.add(port_name)

            self.images.setdefault(self.clean_name(port_name), {})[image_type] = file_name.name

        for port_name in (all_ports - seen_ports):
            logger.warning(f"Port image {port_name}: missing.")

    def _update_images(self):
        """
        Bring the port images up to date, incrementally if possible.
        """
        self.hm.callback.message("  - {}".format(_("Fetching info")))

        if 'images.zip' not in self._data:
            return

        if 'images.000.zip' in self._data and self._update_images_incremental():
            return

        self._update_images_full()

    def _update_images_incremental(self):
        """
        Update the images from the images.NNN.zip files, only downloading the ones that changed.

        Returns False if that isn't possible, then the full images.zip is used.
        """
        img_id = 0

        images_data = None

        if self._images_json_file.is_file():
            with open(self._images_json_file, 'r') as fh:
                images_data = json_safe_load(fh)

        if images_data is None:
            return False

        if "images.zip" not in images_data:
            # It's an older version without the `images.zip` md5sum recorded.
            return False

        # Find all the current images.
        images_to_delete = [
            file_name
            for file_name in self._images_dir.iterdir()
            if file_name.suffix in ('.png', '.jpg')]

        # See how many images.xxx.zip files need updating.
        images_zip_threshold = 0
        for img_id in range(1000):
            zip_xxx_name = f'images.{img_id:03d}.zip'

            if zip_xxx_name not in self._data:
                break

            images_zip_md5 = self._data[zip_xxx_name]['md5']

            # Has this zip been updated?
            images_local_md5 = images_data.get(zip_xxx_name, {}).get('md5', None)

            if images_local_md5 != images_zip_md5:
                # This was negative for some reason?
                images_zip_threshold += 1

        if images_zip_threshold > self.MAX_IMAGES_XXX_ZIP:
            # Yeah lets just download the big zip again.
            return False

        for img_id in range(1000):
            zip_xxx_name = f'images.{img_id:03d}.zip'

            if zip_xxx_name not in self._data:
                break

            images_zip_url = self._data[zip_xxx_name]['url']
            images_zip_md5 = self._data[zip_xxx_name]['md5']

            # Has this zip been updated?
            images_local_md5 = images_data.get(zip_xxx_name, {}).get('md5', None)
            if images_local_md5 == images_zip_md5:
                # This zip file hasn't been updated, mark all images from this zip as okay.
                for image_name in images_data[zip_xxx_name]['images']:
                    file_name = (self._images_dir / image_name)

                    if file_name in images_to_delete:
                        images_to_delete.remove(file_name)

                continue

            logger.debug(f"images_zip_md5={images_zip_md5} != images_local_md5={images_local_md5}")

            # fetch the new archive
            images_zip = net.download(self.hm.temp_dir / zip_xxx_name, images_zip_url, images_zip_md5, callback=self.hm.callback)
            if images_zip is None:
                # Abort, lets just fallback to tried and true images.zip
                logger.debug(f"Unable to download {images_zip_url}")
                return False

            images_data[zip_xxx_name] = {}
            images_data[zip_xxx_name]['md5'] = images_zip_md5
            images_data[zip_xxx_name]['images'] = []

            # unzip the files, keep only png & jpg files
            with zipfile.ZipFile(images_zip, 'r') as zf:
                for zip_name in zf.namelist():
                    if zip_name.casefold().rsplit('.')[-1] not in ('jpg', 'png'):
                        continue

                    clean_name = self.clean_name(zip_name.rsplit('/', 1)[-1])

                    # Keep track of the files in this zip
                    images_data[zip_xxx_name]['images'].append(clean_name)

                    file_name = self._images_dir / clean_name
                    if file_name not in images_to_delete:
                        logger.debug(f"adding {file_name}")

                    with open(file_name, 'wb') as fh:
                        fh.write(zf.read(zip_name))

                    # Mark the files for keeping.
                    if file_name in images_to_delete:
                        images_to_delete.remove(file_name)

            # delete the sucker.
            images_zip.unlink()

        # delete any images not listed in any zip file.
        for image_to_delete in images_to_delete:
            logger.debug(f"removing {image_to_delete}")
            image_to_delete.unlink()

        # We got here, update the images.zip entry in the images_data
        images_data["images.zip"] = self._data['images.zip']['md5']

        with open(self._images_json_file, 'w') as fh:
            json.dump(images_data, fh, indent=4, sort_keys=True)

        self._images_md5_file.write_text(self._data['images.zip']['md5'])
        self._images_md5 = self._data['images.zip']['md5']

        return True

    def _update_images_full(self):
        """
        Update the images from images.zip, if its md5 changed.
        """
        if 'images.000.zip' in self._data:
            images_data = None

            if self._images_json_file.is_file():
                with open(self._images_json_file, 'r') as fh:
                    images_data = json_safe_load(fh)

            if images_data is None:
                images_data = {}

            # we use the md5 stored in the images.json instead.
            self._images_md5 = images_data.get('images.zip', None)

        images_url_zip = self._data['images.zip']['url']

        if 'md5' in self._data['images.zip']:
            images_md5 = self._data['images.zip']['md5']

        else:
            images_url_md5 = self._data['images.zip.md5']['url']
            images_md5 = net.fetch_text(images_url_md5).strip().split(' ', 1)[0]

        if self._images_md5 is None or images_md5 != self._images_md5:
            logger.debug(f"images_md5={images_md5}, self.images_md5={self._images_md5}")
            images_zip = net.download(self.hm.temp_dir / "images.zip", images_url_zip, images_md5, callback=self.hm.callback)
            if images_zip is None:
                logger.debug(f"Unable to download {images_url_zip}")
                return

            images_to_delete = [
                file_name
                for file_name in self._images_dir.iterdir()
                if file_name.suffix in ('.png', '.jpg')]

            with zipfile.ZipFile(images_zip, 'r') as zf:
                for zip_name in zf.namelist():
                    if zip_name.casefold().rsplit('.')[-1] not in ('jpg', 'png'):
                        continue

                    file_name = self._images_dir / self.clean_name(zip_name.rsplit('/', 1)[-1])
                    if file_name not in images_to_delete:
                        logger.debug(f"adding {file_name}")

                    with open(file_name, 'wb') as fh:
                        fh.write(zf.read(zip_name))

                    if file_name in images_to_delete:
                        images_to_delete.remove(file_name)

            for image_to_delete in images_to_delete:
                logger.debug(f"removing {image_to_delete}")
                image_to_delete.unlink()

            if 'images.000.zip' in self._data and 'images' in self._data['images.000.zip']:
                # build up the images.json with the data we have
                images_data = {}

                for img_id in range(1000):
                    zip_xxx_name = f'images.{img_id:03d}.zip'

                    if zip_xxx_name not in self._data:
                        break

                    images_zip_md5 = self._data[zip_xxx_name]['md5']

                    images_data[zip_xxx_name] = {}
                    images_data[zip_xxx_name]['md5'] = images_zip_md5
                    images_data[zip_xxx_name]['images'] = self._data[zip_xxx_name]['images'][:]

                images_data['images.zip'] = images_md5

                with open(self._images_json_file, 'w') as fh:
                    json.dump(images_data, fh, indent=4, sort_keys=True)

            self._images_md5_file.write_text(images_md5)
            self._images_md5 = images_md5

    ## Port lookups
    def download(self, port_name, temp_dir=None, md5_result=None):
        if md5_result is None:
            md5_result = [None]

        if port_name not in self._data:
            logger.error(f"Unable to find port {port_name}")
            self.hm.callback.message_box(_("Unable to find {port_name}.").format(port_name=port_name))
            return None

        if temp_dir is None:
            file_size = self._data[port_name]['size']

            if file_size > HM_MAX_TEMP_SIZE:
                temp_dir = self.hm.ports_dir
            else:
                temp_dir = self.hm.temp_dir

        md5_result[0] = self._data[port_name]['md5']
        zip_file = net.download(temp_dir / port_name, self._data[port_name]['url'], self._data[port_name]['md5'], callback=self.hm.callback)

        if zip_file is None:
            return None

        if port_name in self.utils:
            ## Utils
            return zip_file

        zip_info = port_info_load({})

        zip_info['name'] = port_name
        zip_info['status'] = {
            'source': self._config['name'],
            'md5':    md5_result[0],
            'status': 'downloaded',
            }
        zip_info['zip_file'] = zip_file

        port_info = self.port_info(port_name)
        port_info_merge(zip_info, port_info)

        return zip_info

    def port_info(self, port_name):
        port_name = self.clean_name(port_name)

        if port_name not in getattr(self, '_info', {}):
            return {}

        return self._info[port_name]

    def port_download_size(self, port_name, check_runtime=True):
        port_name = self.clean_name(port_name)

        if port_name not in getattr(self, '_data', {}):
            return 0

        size = self._data[port_name]['size']

        if check_runtime and port_name in getattr(self, '_info', {}):
            port_info = self._info[port_name]

            if len(port_info['attr'].get('runtime', [])) > 0:
                for runtime in port_info['attr']['runtime']:
                    runtime_file = (self.hm.libs_dir / runtime)
                    if not runtime_file.exists():
                        size += self.hm.port_download_size(runtime)

        return size

    def port_download_url(self, port_name):
        port_name = self.clean_name(port_name)

        if port_name not in getattr(self, '_data', {}):
            return None

        return self._data[port_name]['url']
