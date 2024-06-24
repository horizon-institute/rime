import os
import posixpath

from .ensuredir import ensuredir
from . import metadata
from ..sql import sqlite3_connect_filename as sqlite3_connect_with_regex_support

from logging import getLogger
log = getLogger(__name__)


class FSLibFilesystem:
    def __init__(self, _fs, metadata_db_path):
        self._fs = _fs
        self.metadata = metadata.MetadataDb(metadata_db_path)

    def dirname(self, pathname):
        if '/' not in pathname:
            return '/'

        return pathname[:pathname.rindex('/')]

    def basename(self, pathname):
        if '/' not in pathname:
            return pathname

        return pathname[pathname.rindex('/') + 1:]

    def exists(self, path):
        return self._fs.exists(path)

    def getsize(self, path):
        return self._fs.getsize(path)

    def open(self, path):
        return self._fs.open(path, 'rb')

    def stat(self, pathname):
        return os.stat(self._fs.getsyspath(pathname))

    def scandir(self, path):
        pathnames = [posixpath.join(path, name) for name in self._fs.listdir(path)]

        return metadata.get_dir_entries_and_update_db(self, self.metadata, pathnames)

    def create_file(self, path):
        ensuredir(self._fs.getsyspath(path))

        return self._fs.open(path, 'wb')

    def sqlite3_connect(self, path, read_only=True):
        return sqlite3_connect_with_regex_support(self._fs.getsyspath(path), read_only=read_only)

    def sqlite3_create(self, path):
        syspath = self._fs.getsyspath(path)

        ensuredir(syspath)

        return sqlite3_connect_with_regex_support(syspath, read_only=False)

    def get_dir_entry(self, path):
        return metadata.get_dir_entry_and_update_db(self, self.metadata, path)
