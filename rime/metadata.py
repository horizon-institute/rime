"""
Maintain a per-filesystem metadata cache.

Metadata includes the MIME type and the DirEntry only, currently. It's currently stored in-memory but may eventually
move to a database.
"""
from dataclasses import dataclass
from filetype import guess as filetype_guess
from filetype.types.base import Type as FileTypeType

from .filesystem.base import DirEntry


# Chosen by fair dice roll.
# Just kidding, chosen by reference to https://github.com/h2non/filetype.py
FILE_HEADER_GUESS_LENGTH = 261


@dataclass
class Metadata:
    """
    Metadata about a file.
    """
    dir_entry: DirEntry
    filetype: FileTypeType

    @classmethod
    def from_direntry(cls, fs, direntry):
        with fs.open(direntry.path) as f:
            first_bytes = f.read(FILE_HEADER_GUESS_LENGTH)

        if not first_bytes:
            raise ValueError(f'File {direntry.path} is empty')

        filetype = filetype_guess(first_bytes)

        return cls(direntry, filetype)


class FsMetadata:
    def __init__(self):
        self._cache = {}  # maps direntry path to Metadata

    def get(self, fs, direntry: DirEntry):
        if direntry not in self._cache:
            try:
                self._cache[direntry.path] = Metadata.from_direntry(fs, direntry)
            except ValueError:
                self._cache[direntry.path] = None

        return self._cache[direntry.path]


_metadata_by_fs = {}  # FS ID to Metadata


def get_fs_metadata(fs):
    if fs.id_ not in _metadata_by_fs:
        _metadata_by_fs[fs.id_] = FsMetadata()
    return _metadata_by_fs[fs.id_]
