"""
Anonymise a data set by removing PII.

Will always return the same anonymised data for the same input data. This may reduce the anonymity of the data,
but ensures that phone number, etc, correlations can still be made across anonymised data sets.
"""
import re

import phonenumbers


class AnonymisationFailed(Exception):
    pass


RE_PHONE = re.compile(r'\+?[0-9 -]{8,15}')
RE_EMAIL = re.compile(r'[^@]+@[^@]+\.[^@]+')


def canonicalise_phone_number(phone_number, country_code):
    """
    Return the E164 representation of phone_number if possible, or the original number otherwise.

    country_code is the alpha-2 country code and should be set to the country code of the
        device from which the number was obtained.
    """
    try:
        number = phonenumbers.parse(phone_number, country_code)
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.phonenumberutil.NumberParseException:
        return phone_number


class _AnonMap:
    """
    Stores the mapping between original and anonymised information.
    """
    def __init__(self):
        self._next_phone = 1
        self._next_email = 1
        self._anon_email = {}  # email address to anonymised email address
        self._anon_phone = {}  # canonicalise_phone_number(original phone number) to anonymised phone number

    def anonymise_phone(self, phone):
        if phone not in self._anon_phone:
            def _same_length(lgt):
                # Return 111...<next phone> to a length lgt (or length of next phone if longer)
                next_phone_str = str(self._next_phone)
                num_filler = max(0, lgt - len(next_phone_str))
                return '0' * num_filler + next_phone_str

            if phone.startswith('+'):
                # Try to keep the country code.
                anon = phone[:3] + _same_length(len(phone) - 3)
            else:
                anon = _same_length(len(phone))

            self._next_phone += 1
            self._anon_phone[phone] = anon

        return self._anon_phone[phone]

    def anonymise_email(self, email):
        if email not in self._anon_email:
            self._anon_email[email] = f'anon-{self._next_email}@example.com'
            self._next_email += 1

        return self._anon_email[email]


class DBAnonymiser:
    """
    Anonymises a named sqlite3 database.
    """
    def __init__(self, *, rime, fs, db_path, anon_map):
        self.rime = rime
        self.fs = fs
        self.db_path = db_path
        self.anon_map = anon_map
        self.conn = None

    def __enter__(self):
        if not self.conn:
            self.conn = self.fs.sqlite3_connect(self.db_path, read_only=False)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn:
            if exc_type is None:
                self.conn.commit()
            self.conn.close()
            self.conn = None

        return False

    def anonymise_phone(self, table, column):
        def _new_phone(match_obj):
            orig_phone = canonicalise_phone_number(match_obj.group(0), 'GB')
            return self.anon_map.anonymise_phone(orig_phone)

        self.anonymise_regex(table, column, RE_PHONE, _new_phone)

    def anonymise_email(self, table, column):
        def _new_email(match_obj):
            orig_email = match_obj.group(0)
            return self.anon_map.anonymise_email(orig_email)

        self.anonymise_regex(table, column, RE_EMAIL, _new_email)

    def anonymise_name(self, table, column):
        for plugin in self.rime.plugins.get('anonymise', []):
            if plugin.config.get('anonymises') == 'name':
                self._do_db_anonymisation(table, column, plugin.fn)

    def anonymise_regex(self, table, column, regex, replace_fn):
        def _do_regex_replacement(value):
            return regex.sub(replace_fn, value)

        return self._do_db_anonymisation(table, column, _do_regex_replacement)

    def _do_db_anonymisation(self, table, column, cb):
        assert self.conn, 'DBAnonymiser must be used as a context manager'

        for row in self.conn.execute(f'SELECT rowid, {column} FROM {table}'):
            rowid, value = row
            if isinstance(value, str):
                new_value = cb(value)
                if new_value != value:
                    self.conn.execute(f'UPDATE {table} SET {column} = ? WHERE rowid = ?', (new_value, rowid))


class Anonymiser:
    """
    Stores the anonymous map and can create DBAnonymisers for providers. Instantiated by graphql layer.
    """
    def __init__(self, rime):
        self.rime = rime
        self.anon_map = _AnonMap()

    def db_anonymiser(self, fs, db_path):
        return DBAnonymiser(rime=self.rime, fs=fs, db_path=db_path, anon_map=self.anon_map)

    def anonymise_device_provider(self, device, provider):
        """
        Anonymises a device IN-PLACE -- expected to be called from the graphql layer on a new subsetted device as part
        of the anonymisation process.
        """
        if provider.PII_FIELDS is NotImplemented:
            raise AnonymisationFailed(f'Provider {provider} has not implemented PII_FIELDS')

        if not isinstance(provider.PII_FIELDS, dict):
            raise AnonymisationFailed(f'Provider {provider} has invalid PII_FIELDS')

        for storage_method, args in provider.PII_FIELDS.items():
            handler = getattr(self, f'_anonymise_device_provider_{storage_method}')
            handler(device, provider, args)

    def _anonymise_device_provider_sqlite3(self, device, provider, args):
        for db_path, tables in args.items():
            with DBAnonymiser(rime=self.rime, fs=device.fs, db_path=db_path, anon_map=self.anon_map) as db_anonymiser:
                for table_name, columns in tables.items():
                    for column_name, field_anonymiser in columns.items():
                        try:
                            self._anonymise_device_provider_sqlite3_field(db_anonymiser, table_name,
                                                                          column_name, field_anonymiser)
                        except Exception as e:
                            raise AnonymisationFailed('Failed to anonymise {0} {1}.{2}: {3}'.format(
                                                        provider.NAME, table_name, column_name, e))

    def _anonymise_device_provider_sqlite3_field(self, db_anonymiser, table_name, column_name, field_anonymiser):
        if not isinstance(field_anonymiser, set):
            field_anonymiser = {field_anonymiser}

        for callable in field_anonymiser:
            callable(db_anonymiser, table_name, column_name)


def anonymise_phone(db_anonymiser, table_name, column_name):
    db_anonymiser.anonymise_phone(table_name, column_name)


def anonymise_email(db_anonymiser, table_name, column_name):
    db_anonymiser.anonymise_email(table_name, column_name)


def anonymise_name(db_anonymiser, table_name, column_name):
    db_anonymiser.anonymise_name(table_name, column_name)
