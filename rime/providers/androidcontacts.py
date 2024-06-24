# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

"""
Provides com.android.providers.contacts

As per https://developer.android.com/guide/topics/providers/contacts-provider,
the raw_contacts table stores one contact per account. These raw contacts link
to the contacts table, which has one row per actual contact.

The actual data is stored in the data table. Each type of contact data has its own
MIME type (stored in the mimetypes table), and the data table has foreign keys both
to the MIME types and raw_contacts table.

So to find contacts, walk the contacts table, collecting all associated raw_contacts
IDs. For each collection, look for MIME types of interest in the data table.
"""

from typing import Iterable
from dataclasses import dataclass

from ..provider import Provider
from ..event import Event
from ..sql import Table, Query, get_field_indices
from ..contact import Contact, Name
from ..anonymise import anonymise_phone, anonymise_email, anonymise_name

from .providernames import ANDROID_CONTACTS, ANDROID_CONTACTS_FRIENDLY


@dataclass
class AndroidContact:
    contact_row_id: str
    raw_contact_row_ids: set[str]


# Maps filesystem identifier to {id: mime type}
MIMETYPE_TO_ID = {}

# Mimetypes we're interested in, mapping from android to our class.
MIMETYPES = {
    'vnd.android.cursor.item/name': 'name.display',
    'vnd.android.cursor.item/phone_v2': 'phone',
    'vnd.android.cursor.item/email_v2': 'email',
}


def filter_contacts(filter, contacts_iterable):
    if not filter:
        return contacts_iterable

    return [contact for contact in contacts_iterable
            if filter.name_regex.match(contact.name.display)]


class AndroidContacts(Provider):
    NAME = ANDROID_CONTACTS
    FRIENDLY_NAME = ANDROID_CONTACTS_FRIENDLY

    DB_PATH = 'data/data/com.android.providers.contacts/databases/contacts2.db'

    def __init__(self, fs):
        self.fs = fs

    def _db(self):
        return self.fs.sqlite3_connect(self.DB_PATH, read_only=True)

    def is_version_compatible(self):
        # Android 10:
        # sqlite> pragma user_version;
        # 329080
        return True

    def search_events(self, device, filter_):
        return []

    def search_contacts(self, contacts_filter):
        mime_type_id_to_name = self._get_mime_types()

        contact_table = Table('contacts')
        raw_contact_table = Table('raw_contacts')
        data_table = Table('data')

        query = Query.from_(contact_table)\
            .join(raw_contact_table)\
            .on(contact_table.name_raw_contact_id == raw_contact_table._id)\
            .join(data_table)\
            .on(raw_contact_table._id == data_table.raw_contact_id)\
            .select(contact_table._id, contact_table.name_raw_contact_id, data_table.mimetype_id, data_table.data1)\
            .where(data_table.mimetype_id.isin(list(mime_type_id_to_name.keys())))

        fields = get_field_indices(query)
        contacts = {}  # Indexed by contact ID

        with self._db() as conn:
            for row in conn.execute(str(query)):
                contact_id = row[fields['_id']]
                raw_contact_id = row[fields['name_raw_contact_id']]
                mime_type_id = row[fields['mimetype_id']]
                data = row[fields['data1']]

                if contact_id not in contacts:
                    provider_data = AndroidContact(contact_row_id=contact_id, raw_contact_row_ids=set())
                    contacts[contact_id] = Contact(
                        local_id=contact_id,
                        device_id=self.fs.id_,
                        name=Name(),
                        providerName=self.NAME,
                        providerFriendlyName=self.FRIENDLY_NAME,
                        provider_data=provider_data
                    )

                contacts[contact_id].provider_data.raw_contact_row_ids.add(raw_contact_id)

                contact_field_name = MIMETYPES[mime_type_id_to_name[mime_type_id]]
                setattr(contacts[contact_id], contact_field_name, data)

        return list(filter_contacts(contacts_filter, contacts.values()))

    PII_FIELDS = {
        'sqlite3': {
            DB_PATH: {
                'contacts': {
                    'default_number': anonymise_phone,
                },
                'raw_contacts': {
                    'sync1': anonymise_phone,
                },
                'data': {
                    'data1': {anonymise_phone, anonymise_email, anonymise_name},
                    'data2': {anonymise_phone, anonymise_email, anonymise_name},
                    'data3': {anonymise_phone, anonymise_email, anonymise_name},
                    'data4': {anonymise_phone, anonymise_email, anonymise_name},
                }
            }
        }
    }

    def subset(self, subsetter, events: Iterable[Event], contacts: Iterable[Contact]):
        with self._db() as conn:
            with subsetter.db_subset(src_conn=conn, new_db_pathname=self.DB_PATH) as db_subset:
                rows_contacts = db_subset.row_subset('contacts', '_id')
                rows_raw_contacts = db_subset.row_subset('raw_contacts', '_id')
                rows_data = db_subset.row_subset('data', 'raw_contact_id')
                db_subset.complete_table('mimetypes')

                for contact in contacts:
                    if contact.providerName != self.NAME:
                        continue

                    rows_contacts.add(contact.local_id)
                    rows_raw_contacts.update(contact.provider_data.raw_contact_row_ids)
                    rows_data.update(contact.provider_data.raw_contact_row_ids)

    def all_files(self):
        # TODO
        return []

    def _get_mime_types(self):
        """
        Returns a dict of {id: mime type} for the given filesystem.
        """
        fs_id = self.fs.id_

        if fs_id not in MIMETYPE_TO_ID:
            mime_type_table = Table('mimetypes')
            query = Query.from_(mime_type_table)\
                .select('_id', 'mimetype')\
                .where(mime_type_table.mimetype.isin(list(MIMETYPES.keys())))

            fields = get_field_indices(query)
            result = {}

            with self._db() as conn:
                for row in conn.execute(str(query)):
                    result[row[fields['_id']]] = row[fields['mimetype']]

            MIMETYPE_TO_ID[fs_id] = result

        return MIMETYPE_TO_ID[fs_id]

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
