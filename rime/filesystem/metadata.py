"""
Maintain a per-filesystem metadata cache.

This is used internally by filesystems and exposed through filesystem datastructures such as DirEntry.
"""
import os
import pickle

from dataclasses import dataclass

from .direntry import DirEntry

from ..sql import sqlite3_connect_filename, Table, Query, Column, Parameter
from .direntry import DirEntry


class MetadataDb:
    def __init__(self, db_pathname):
        self.settings_table = Table('settings')
        self.dir_entries_table = Table('dir_entries')
        self.mime_types_table = Table('mime_types')

        self.db = self._init_db(db_pathname)

    def _init_db(self, db_pathname):
        if not os.path.exists(os.path.dirname(db_pathname)):
            os.makedirs(os.path.dirname(db_pathname))

        conn = sqlite3_connect_filename(db_pathname, read_only=False)

        query = "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        conn.execute(query)

        query = "CREATE TABLE IF NOT EXISTS mime_types (id INTEGER PRIMARY KEY AUTOINCREMENT, mime_type TEXT)"
        conn.execute(query)

        query = "CREATE TABLE IF NOT EXISTS dir_entries (" +\
            "id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, mime_type_id INTEGER, stat_val TEXT)"
        conn.execute(query)

        return conn

    @classmethod
    def get_for_filesystem_name(cls, config, filesystem_name):
        metadata_dir = config.get_pathname('metadata.base_path')
        metadata_filename = os.path.join(metadata_dir, filesystem_name + '.sqlite3')
        return cls(metadata_filename)

    # Methods to use the settings table.
    def _get_setting(self, key):
        query = Query.select(self.settings_table).where(self.settings_table.key == key)
        result = self.db.execute(query).fetchone()

        if result is None:
            return None

        return result['value']

    def _set_setting(self, key, value):
        query = Query.into(self.settings_table).insert(key=key, value=value).on_duplicate_key_update(value=value)
        self.db.execute(str(query))

    def is_subset_fs(self):
        return self._get_setting('subset_fs') == '1'

    def set_subset_fs(self, is_subset_fs):
        self._set_setting('subset_fs', '1' if is_subset_fs else '0')

    def is_locked(self):
        return self._get_setting('locked') == '1'

    def set_locked(self, is_locked):
        self._set_setting('locked', '1' if is_locked else '0')

    def is_encrypted(self):
        return self._get_setting('encrypted') == '1'

    def set_encrypted(self, is_encrypted):
        self._set_setting('encrypted', '1' if is_encrypted else '0')

    # Methods to use the dir_entries table.
    def get_dir_entries_for_pathnames(self, pathnames: list[str]) -> list[DirEntry]:
        """
        Get DirEntries for the given pathnames and return the results.

        One or more pathnames may be missing in which case they will just not be returned. Filesystems
        are expected to call add_dir_entries_for_pathnames() to add the entries.
        """
        query = Query \
            .from_(self.dir_entries_table) \
            .join(self.mime_types_table).on(self.dir_entries_table.mime_type_id == self.mime_types_table.id) \
            .select(self.dir_entries_table.id, self.dir_entries_table.path,
                    self.mime_types_table.mime_type, self.dir_entries_table.stat_val) \
            .where(self.dir_entries_table.path.isin(pathnames))
        results = self.db.execute(str(query)).fetchall()

        return [DirEntry(path=result[1], stat_val=pickle.loads(result[3]),
                         mime_type=result[2]) for result in results]

    def add_dir_entries_for_pathnames(self, dir_entries: list[DirEntry]):
        """
        Add DirEntries for the given pathnames.

        The pathnames must not already exist in the database.
        """
        # Create or update mime type IDs from mime types.
        query = Query \
            .from_(self.mime_types_table) \
            .select(self.mime_types_table.id, self.mime_types_table.mime_type) \
            .where(self.mime_types_table.mime_type.isin([dir_entry.mime_type for dir_entry in dir_entries]))
        results = self.db.execute(str(query)).fetchall()

        mime_type_ids = {result[1]: result[0] for result in results}  # map mime type to ID
        mime_types_to_add = [dir_entry.mime_type for dir_entry in dir_entries if dir_entry.mime_type not in mime_type_ids]

        if mime_types_to_add:
            query = Query\
                .into(self.mime_types_table)\
                .columns('mime_type')\
                .insert(Parameter('?'))
            self.db.executemany(str(query), [(typ,) for typ in mime_types_to_add])

            query = Query\
                .from_(self.mime_types_table)\
                .select(self.mime_types_table.id, self.mime_types_table.mime_type)\
                .where(self.mime_types_table.mime_type.isin(mime_types_to_add))
            results = self.db.execute(str(query)).fetchall()

            mime_type_ids.update({result[1]: result[0] for result in results})  # map mime type to ID

        # Add the dir entries.
        query = Query\
            .into(self.dir_entries_table)\
            .columns('path', 'mime_type_id', 'stat_val')\
            .insert(Parameter('?'), Parameter('?'), Parameter('?'))

        parameters = [
            (dir_entry.path, mime_type_ids[dir_entry.mime_type], pickle.dumps(dir_entry.stat_val))
            for dir_entry in dir_entries
        ]

        self.db.executemany(str(query), parameters)


def get_dir_entries_and_update_db(fs, metadata_db, pathnames: list[str]) -> list[DirEntry]:
    """
    Get DirEntries for the given pathnames and return the results. If pathnames are
    missing, add them to the database.

    Used internally by filesystem implementations.
    """
    dir_entries = metadata_db.get_dir_entries_for_pathnames(pathnames)

    found_pathnames = set([dir_entry.path for dir_entry in dir_entries])
    pathnames_to_add = [pathname for pathname in pathnames if pathname not in found_pathnames]

    if pathnames_to_add:
        dir_entries_to_add = [fs.path_to_direntry(pathname) for pathname in pathnames_to_add]
        metadata_db.add_dir_entries_for_pathnames(dir_entries_to_add)
        dir_entries.extend(dir_entries_to_add)

    return dir_entries
