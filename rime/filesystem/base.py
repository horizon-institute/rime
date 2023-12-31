# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
from typing import Optional

from .direntry import DirEntry


@dataclass(frozen=True, unsafe_hash=True)
class File:
    """
    """
    pathname: str
    mime_type: Optional[str] = None


class DeviceFilesystem(ABC):
    """
    Provides unified access to a device's filesystem.
    """
    @classmethod
    @abstractmethod
    def is_device_filesystem(cls, path) -> bool:
        """
        Is this path the root of a filesystem this class can manage?

        Implementing classes may return False to this call if the path is not a filesystem of the type they're
        expecting.
        """
        return False

    @classmethod
    @abstractmethod
    def create(cls, id_: str, root: str, template: Optional['DeviceFilesystem'] = None) -> 'DeviceFilesystem':
        """
        Create a new filesystem of this type at 'path'.
        """
        raise NotImplementedError()

    @abstractmethod
    def is_subset_filesystem(self) -> bool:
        """
        Is this a subset filesystem?
        """
        return False

    @abstractmethod
    def scandir(self, path) -> list[DirEntry]:
        """
        As os.scandir().
        """
        return []

    @abstractmethod
    def exists(self, path) -> bool:
        """
        As os.path.exists().
        """
        return False

    @abstractmethod
    def getsize(self, path) -> int:
        """
        As os.path.getsize().
        """
        return 0

    @abstractmethod
    def open(self, path):
        """
        As open().
        """
        return None

    @abstractmethod
    def create_file(self, path):
        """
        As open(path, 'wb').
        """
        return None

    @abstractmethod
    def sqlite3_connect(self, path, read_only=True):
        """
        Return an opened sqlite3 connection to the database at 'path'.
        """
        return None

    @abstractmethod
    def sqlite3_create(self, path):
        """
        Create a new sqlite3 database at 'path' and return an opened connection read-write to it.
        """
        return None

    @abstractmethod
    def lock(self, locked: bool):
        """
        Lock or unlock the filesystem. A locked filesystem can't be viewed or written to.
        """
        pass

    @abstractmethod
    def is_locked(self) -> bool:
        """
        Is the filesystem locked?
        """
        return False

    def walk(self, path):
        for entry in self.scandir(path):
            if entry.is_dir():
                yield from self.walk(entry.path)
            else:
                yield entry

    @abstractmethod
    def dirname(self, pathname):
        raise NotImplementedError(pathname)

    @abstractmethod
    def basename(self, pathname):
        raise NotImplementedError(pathname)

    @abstractmethod
    def stat(self, pathname):
        raise NotImplementedError(pathname)

    @abstractmethod
    def path_to_direntry(self, path) -> DirEntry:
        raise NotImplementedError()

    def is_encrypted(self) -> bool:
        return False

    def decrypt(self, passphrase: str) -> bool:
        raise NotImplementedError()
