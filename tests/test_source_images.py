# SPDX-License-Identifier: MIT
#
# PortMasterV3 port screenshot updates: the full images.zip and the
# incremental images.NNN.zip paths.

import hashlib
import io
import json
import zipfile

import pytest

from harbourmaster import source as hm_source
from harbourmaster.util import net as hm_net


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        for name, data in files.items():
            ## A fixed date: the same files must give the same zip (and md5), however slow the device.
            zf.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data)

    return buffer.getvalue()


def md5(data):
    return hashlib.md5(data).hexdigest()


class FakeImageServer:
    """
    Builds a ports.json whose utils hold images.zip and optionally images.NNN.zip
    entries, and serves those zips to net.download.
    """

    def __init__(self, base_ports_json, monkeypatch):
        self.base = base_ports_json
        self.blobs = {}
        self.downloads = []
        self.ports_json = None
        ## Publish only images.zip, like sources without images.NNN.zip.
        self.only_full = False

        monkeypatch.setattr(hm_net, "fetch_json", lambda url: json.loads(json.dumps(self.ports_json)))
        monkeypatch.setattr(hm_net, "download", self.download)

    def download(self, file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
        self.downloads.append(file_url.rsplit('/', 1)[-1])
        file_name.write_bytes(self.blobs[file_url])
        return file_name

    def _asset(self, name, data, extra=None):
        url = f"https://example.com/release/{name}"
        self.blobs[url] = data
        asset = {'name': name, 'size': len(data), 'md5': md5(data), 'url': url}
        asset.update(extra or {})
        return asset

    def publish(self, split_zips):
        """
        split_zips: list of {image name: bytes}, one per images.NNN.zip. An empty
        list publishes only images.zip. images.zip always holds every image.
        """
        all_images = {}
        for images in split_zips:
            all_images.update(images)

        if not split_zips:
            raise ValueError("need at least one group of images")

        data = json.loads(json.dumps(self.base))
        utils = {name: asset for name, asset in data['utils'].items() if not name.startswith('images')}
        utils['images.zip'] = self._asset('images.zip', zip_bytes(all_images))

        if not self.only_full:
            for i, images in enumerate(split_zips):
                name = f'images.{i:03d}.zip'
                utils[name] = self._asset(name, zip_bytes(images), {'images': sorted(images)})

        data['utils'] = utils
        self.ports_json = data
        self.downloads.clear()


@pytest.fixture
def server(ports_json_data, monkeypatch):
    return FakeImageServer(ports_json_data, monkeypatch)


@pytest.fixture
def update_source(make_hm):
    """Update the PortMaster source like a fresh start of PortMaster would."""
    def _update():
        hm = make_hm()
        source = hm.sources['pm']
        source.update()
        return source

    return _update


def image_files(source):
    return sorted(p.name for p in source._images_dir.iterdir() if p.suffix in ('.png', '.jpg'))


GROUP_A = {
    '100liljumps.screenshot.png': b'jumps-1',
    'sprout.screenshot.png': b'sprout-1',
    }
GROUP_B = {
    '2048plus.screenshot.jpg': b'2048-1',
    'starfighter.screenshot.png': b'star-1',
    'starfighter.cover.png': b'star-cover-1',
    }


################################################################################
## images.zip only
def test_full_images_zip(server, update_source):
    server.only_full = True
    server.publish([{**GROUP_A, **GROUP_B}])

    source = update_source()

    assert server.downloads == ['images.zip']
    assert image_files(source) == sorted({**GROUP_A, **GROUP_B})
    assert (source._images_dir / 'sprout.screenshot.png').read_bytes() == b'sprout-1'
    assert source._images_md5_file.read_text() == server.ports_json['utils']['images.zip']['md5']

    assert source.images['100liljumps.zip'] == {'screenshot': '100liljumps.screenshot.png'}
    assert source.images['starfighter.zip'] == {'screenshot': 'starfighter.screenshot.png', 'cover': 'starfighter.cover.png'}


def test_full_images_zip_unchanged_is_not_downloaded(server, update_source):
    server.only_full = True
    server.publish([GROUP_A])
    update_source()

    server.publish([GROUP_A])
    update_source()

    assert server.downloads == []


def test_full_images_zip_removes_stale_images(server, update_source):
    server.only_full = True
    server.publish([{**GROUP_A, **GROUP_B}])
    update_source()

    server.publish([GROUP_A])
    source = update_source()

    assert server.downloads == ['images.zip']
    assert image_files(source) == sorted(GROUP_A)


################################################################################
## images.NNN.zip
def test_first_update_uses_full_zip_and_records_split_zips(server, update_source):
    server.publish([GROUP_A, GROUP_B])

    source = update_source()

    ## No images.json yet, so the incremental path can't be used.
    assert server.downloads == ['images.zip']
    assert image_files(source) == sorted({**GROUP_A, **GROUP_B})

    images_json = json.loads(source._images_json_file.read_text())
    utils = server.ports_json['utils']
    assert images_json == {
        'images.zip': utils['images.zip']['md5'],
        'images.000.zip': {'md5': utils['images.000.zip']['md5'], 'images': sorted(GROUP_A)},
        'images.001.zip': {'md5': utils['images.001.zip']['md5'], 'images': sorted(GROUP_B)},
        }


def test_incremental_update_downloads_only_changed_zips(server, update_source):
    server.publish([GROUP_A, GROUP_B])
    update_source()

    ## starfighter's cover is gone, 2048plus has a new screenshot.
    new_b = {'2048plus.screenshot.jpg': b'2048-2', 'starfighter.screenshot.png': b'star-1'}
    server.publish([GROUP_A, new_b])
    source = update_source()

    assert server.downloads == ['images.001.zip']
    assert image_files(source) == sorted({**GROUP_A, **new_b})
    assert (source._images_dir / '2048plus.screenshot.jpg').read_bytes() == b'2048-2'

    utils = server.ports_json['utils']
    images_json = json.loads(source._images_json_file.read_text())
    assert images_json['images.001.zip'] == {'md5': utils['images.001.zip']['md5'], 'images': sorted(new_b)}
    assert images_json['images.zip'] == utils['images.zip']['md5']
    assert source._images_md5_file.read_text() == utils['images.zip']['md5']


def test_incremental_update_nothing_changed(server, update_source):
    server.publish([GROUP_A, GROUP_B])
    update_source()

    server.publish([GROUP_A, GROUP_B])
    source = update_source()

    assert server.downloads == []
    assert image_files(source) == sorted({**GROUP_A, **GROUP_B})


def test_too_many_changed_zips_uses_full_zip(server, update_source):
    max_changes = hm_source.PortMasterV3.MAX_IMAGES_XXX_ZIP
    groups = [{f'port{i}.screenshot.png': b'v1'} for i in range(max_changes + 2)]
    server.publish(groups)
    update_source()

    ## One more changed zip than the incremental path allows.
    changed = [{f'port{i}.screenshot.png': b'v2'} if i <= max_changes else group for i, group in enumerate(groups)]
    server.publish(changed)
    source = update_source()

    assert server.downloads == ['images.zip']
    assert (source._images_dir / 'port0.screenshot.png').read_bytes() == b'v2'
