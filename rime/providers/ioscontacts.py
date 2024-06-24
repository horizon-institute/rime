# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

"""
Provides ios contacts
"""
from typing import Iterable

from ..provider import Provider
from ..contact import Contact, Name
from ..sql import Table, Query, get_field_indices
from ..event import Event
from ..anonymise import anonymise_phone, anonymise_email, anonymise_name
from .providernames import IOS_CONTACTS, IOS_CONTACTS_FRIENDLY


class IOSContacts(Provider):
    NAME = IOS_CONTACTS
    FRIENDLY_NAME = IOS_CONTACTS_FRIENDLY

    DB_PATH = 'HomeDomain/Library/AddressBook/AddressBook.sqlitedb'

    def __init__(self, fs):
        self.fs = fs

    def _db(self):
        return self.fs.sqlite3_connect(self.DB_PATH, read_only=True)

    def is_version_compatible(self):
        return True

    def search_events(self, device, filter_):
        return []

    # This could probably be tidier!
    # Filter does nothing for now
    def search_contacts(self, filter_):
        person_table = Table('ABPerson')
        mvtable = Table('ABMultiValue')
        # This will return several records per person.
        # Phone numbers will have property=3, emails will have property=4
        # Some may have neither.
        query = Query.from_(person_table).left_join(mvtable).on(person_table.ROWID == mvtable.record_id).select(
            person_table.ROWID, person_table.First, person_table.Last,
            mvtable.property, mvtable.label, mvtable.value
        ).orderby(person_table.ROWID)
        fields = get_field_indices(query)
        prev_id = None
        email = phone = first = last = ""

        # We'll get several rows per contact.
        # These will be ordered by ROWID, so we should get all the values for one contact together.
        with self._db() as conn:
            for row in conn.execute(str(query)):
                rowid = row[fields['ROWID']]
                if rowid != prev_id and prev_id is not None:
                    # Moving on to new contact; return the last one
                    # with whatever we've found
                    yield Contact(
                        local_id=prev_id,
                        device_id=self.fs.id_,
                        providerName=self.NAME,
                        providerFriendlyName=self.FRIENDLY_NAME,
                        name=Name(first=first, last=last),
                        phone=phone,
                        email=email
                    )
                    email = phone = first = last = ""
                first, last = row[fields['First']], row[fields['Last']]
                prev_id = rowid
                if row[fields['property']] == 3:
                    phone = row[fields['value']]
                if row[fields['property']] == 4:
                    email = row[fields['value']]

            # And when we get to the end of the query, we need to return the last one.
            if prev_id is not None:
                yield Contact(
                    local_id=prev_id,
                    device_id=self.fs.id_,
                    providerName=self.NAME,
                    providerFriendlyName=self.FRIENDLY_NAME,
                    name=Name(first=first, last=last),
                    phone=phone,
                    email=email
                )

    PII_FIELDS = {
        'sqlite3': {
            DB_PATH: {
                'ABMultiValue': {
                    'value': {anonymise_phone, anonymise_email, anonymise_name},
                }
            }
        }
    }

    def subset(self, subsetter, events: Iterable[Event], contacts: Iterable[Contact]):
        with self._db() as conn:
            with subsetter.db_subset(src_conn=conn, new_db_pathname=self.DB_PATH) as subset_db:
                abperson_rows = subset_db.row_subset('ABPerson', 'ROWID')
                abmv_rows = subset_db.row_subset('ABMultiValue', 'record_id')

                my_contact_ids = [contact.local_id for contact in contacts if contact.providerName == self.NAME]

                abperson_rows.update(my_contact_ids)
                abmv_rows.update(my_contact_ids)

    def all_files(self):
        # TODO
        return []

    @classmethod
    def from_filesystem(cls, fs):
        if fs.exists(cls.DB_PATH):
            obj = cls(fs)
            if obj.is_version_compatible():
                return obj

        return None

    def get_media(self, local_id):
        """
        Return the pathname, relative to the filesystem, of media identified by 'local_id'.
        """
        raise NotImplementedError()
