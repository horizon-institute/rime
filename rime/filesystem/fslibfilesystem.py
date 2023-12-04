import os

from .base import DirEntry
from .ensuredir import ensuredir
from ..sql import sqlite3_connect_filename as sqlite3_connect_with_regex_support

from logging import getLogger
log = getLogger(__name__)


class FSLibFilesystem:
    def __init__(self, _fs):
        self._fs = _fs

    def dirname(self, pathname):
        if '/' not in pathname:
            return '/'

        return pathname[:pathname.rindex('/')]

    def path_to_direntry(self, path, name=None) -> DirEntry:
        if name is None:
            name = os.path.basename(path)

        syspath = self._fs.getsyspath(path)
        stat_val = os.stat(syspath)
        return DirEntry(name, path, stat_val)

    def scandir(self, path):
        result = []
        for name in self._fs.listdir(path):
            pathname = os.path.join(path, name)  # I love it when a plan comes together
            result.append(self.path_to_direntry(pathname, name))

        return result

    def create_file(self, path):
        ensuredir(self._fs.getsyspath(path))

        return self._fs.open(path, 'wb')

    def sqlite3_connect(self, path, read_only=True):
        return sqlite3_connect_with_regex_support(self._fs.getsyspath(path), read_only=read_only)

    def sqlite3_create(self, path):
        syspath = self._fs.getsyspath(path)

        ensuredir(syspath)

        return sqlite3_connect_with_regex_support(syspath, read_only=False)
