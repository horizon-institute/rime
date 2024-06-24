from contextlib import contextmanager
import posixpath
from ..sql import sqlite3_connect as sqlite3_connect_with_regex_support


class DeviceSettings:
    def __init__(self, path, settings_filename='_rime_settings.db'):
        self._db_name = posixpath.join(path, settings_filename)
        self._init_tables()

    @contextmanager
    def _db(self):
        conn = sqlite3_connect_with_regex_support(self._db_name)
        try:
            yield conn
        finally:
            conn.close()

    def _init_tables(self):
        with self._db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT, value TEXT)")

    def _get_setting(self, key):
        with self._db() as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = c.fetchone()
            if row:
                return row[0]
            else:
                return None

    def _set_setting(self, key, value):
        with self._db() as conn:
            c = conn.cursor()
            c.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
            if c.rowcount == 0:
                c.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

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
