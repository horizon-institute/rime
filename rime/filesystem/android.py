# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd
from typing import Optional
import os
import tempfile
import zipfile

import fs.osfs

from .base import DeviceFilesystem
from .devicesettings import DeviceSettings
from .fslibfilesystem import FSLibFilesystem
from . import zipsupport


class AndroidDeviceFilesystem(DeviceFilesystem):
    def __init__(self, id_: str, root: str, metadata_db_path: str):
        self.id_ = id_
        self._settings = DeviceSettings(root)
        self._fsaccess = FSLibFilesystem(fs.osfs.OSFS(root), metadata_db_path)

    @classmethod
    def is_device_filesystem(cls, path):
        return os.path.exists(os.path.join(path, 'data', 'data', 'android'))

    @classmethod
    def create(cls, id_: str, root: str, metadata_db_path: str, template: Optional[DeviceFilesystem] = None)\
            -> DeviceFilesystem:
        if os.path.exists(root):
            raise FileExistsError(root)

        os.makedirs(root)
        os.makedirs(os.path.join(root, 'data', 'data', 'android'))

        obj = cls(id_, root, metadata_db_path)
        obj._settings.set_subset_fs(True)
        return obj

    @property
    def metadata(self):
        return self._fsaccess.metadata

    def dirname(self, pathname):
        return self._fsaccess.dirname(pathname)

    def basename(self, pathname):
        return self._fsaccess.basename(pathname)

    def stat(self, pathname):
        return self._fsaccess.stat(pathname)

    def is_subset_filesystem(self) -> bool:
        return self._settings.is_subset_fs()

    def scandir(self, path):
        return self._fsaccess.scandir(path)

    def exists(self, path):
        return self._fsaccess.exists(path)

    def getsize(self, path):
        return self._fsaccess.getsize(path)

    def open(self, path):
        return self._fsaccess.open(path)

    def create_file(self, path):
        return self._fsaccess.create_file(path)

    def sqlite3_connect(self, path, read_only=True):
        return self._fsaccess.sqlite3_connect(path, read_only)

    def sqlite3_create(self, path):
        return self._fsaccess.sqlite3_create(path)

    def lock(self, locked: bool):
        self._settings.set_locked(locked)

    def is_locked(self) -> bool:
        return self._settings.is_locked()

    def get_dir_entry(self, path):
        return self._fsaccess.get_dir_entry(path)


class AndroidZippedDeviceFilesystem(DeviceFilesystem):
    """
    Zipped filesystem of an Android device. Currently supports only read mode
    for the data.

    The contents of the .zip file are extracted in a temporary directory
    and then the (only) directory from within the temporary directory
    (the `main_dir`) is used to instantiate a filesystem. All queries
    refer to the data in the temporary directory.
    """

    def __init__(self, id_: str, root: str, metadata_db_path: str):
        self.id_ = id_

        # extract the files from the zipfile in a temporary directory
        self.temp_root = tempfile.TemporaryDirectory()

        with zipfile.ZipFile(root) as zp:
            main_dir = zipsupport.get_zipfile_main_dir(zp)
            zp.extractall(path=self.temp_root.name)

        # instantiate a filesystem from the temporary directory
        self._fs = fs.osfs.OSFS(os.path.join(self.temp_root.name, main_dir.name))
        self._settings = DeviceSettings(os.path.join(self.temp_root.name, main_dir.name))
        self._fsaccess = FSLibFilesystem(self._fs, metadata_db_path)

    @classmethod
    def is_device_filesystem(cls, path):
        if not zipfile.is_zipfile(path):
            return False

        with zipfile.ZipFile(path) as zp:
            # get the main directory contained in the .zip container file
            main_dir = zipsupport.get_zipfile_main_dir(zp)
            return (main_dir / 'data' / 'data' / 'android').exists()

    @classmethod
    def create(cls, id_: str, root: str, metadata_db_path: str, template: Optional['DeviceFilesystem'] = None)\
            -> 'DeviceFilesystem':
        return AndroidDeviceFilesystem.create(id_, root, metadata_db_path)

    def is_subset_filesystem(self) -> bool:
        return self._settings.is_subset_fs()

    def scandir(self, path):
        return self._fsaccess.scandir(path)

    def exists(self, path):
        return self._fs.exists(path)

    def getsize(self, path):
        return self._fs.getsize(path)

    def open(self, path):
        return self._fs.open(path, 'rb')

    def create_file(self, path):
        raise NotImplementedError

    def sqlite3_connect(self, path, read_only=True):
        return self._fsaccess.sqlite3_connect(path, read_only)

    def sqlite3_create(self, path):
        raise NotImplementedError

    def lock(self, locked: bool):
        self._settings.set_locked(locked)

    def is_locked(self) -> bool:
        return self._settings.is_locked()

    def dirname(self, pathname):
        return self._fsaccess.dirname(pathname)

    def basename(self, pathname):
        return self._fsaccess.basename(pathname)

    def stat(self, pathname):
        return self._fsaccess.stat(pathname)

    def get_dir_entry(self, path):
        return self._fsaccess.get_dir_entry(path)
