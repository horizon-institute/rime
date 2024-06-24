# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

"""
SMS / MMS for Android
"""
import datetime
from dataclasses import dataclass

from ..provider import Provider
from .providerutils import LazyContactProvider, LazyContactProviderContacts
from ..event import MessageEvent, MessageSession
from ..sql import Table, Query, get_field_indices
from ..contact import Contact, Name
from ..anonymise import anonymise_phone, anonymise_name
from .providernames import ANDROID_TELEPHONY, ANDROID_TELEPHONY_FRIENDLY

TYPE_TO_ME = 1
TYPE_FROM_ME = 2


@dataclass
class AtMessage:
    threads_table_id: str
    address_table_id: str


class AndroidTelephony(Provider, LazyContactProvider):
    NAME = ANDROID_TELEPHONY
    FRIENDLY_NAME = ANDROID_TELEPHONY_FRIENDLY

    MMSSMS_DB = 'data/data/com.android.providers.telephony/databases/mmssms.db'

    def __init__(self, fs):
        self.fs = fs
        self.contacts = LazyContactProviderContacts(self)
        self.sessions = {}

    def _db(self):
        return self.fs.sqlite3_connect(self.MMSSMS_DB, read_only=True)

    def search_events(self, device, filter_):
        """
        Search for events matching filter_, which is an EventFilter.
        """
        sms_table = Table('sms')
        threads_table = Table('threads')
        address_table = Table('canonical_addresses')
        query = Query\
            .from_(sms_table)\
            .left_join(threads_table).on(sms_table.thread_id == threads_table._id)\
            .left_join(address_table).on(threads_table.recipient_ids == address_table._id)\
            .select(sms_table._id.as_('sms_id'), address_table._id.as_('address_id'), sms_table.thread_id,
                    sms_table.type, sms_table.address, sms_table.date, sms_table.body)

        fields = get_field_indices(query)

        with self._db() as conn:
            for row in conn.execute(query.get_sql()):
                session = self._find_session(row[fields['thread_id']], row[fields['address_id']])

                provider_data = AtMessage(
                    threads_table_id=row[fields['thread_id']],
                    address_table_id=row[fields['address_id']],
                )

                sender = device.device_operator_contact \
                    if row[fields['type']] == TYPE_TO_ME \
                    else self.contacts[row[fields['address_id']]]

                yield MessageEvent(
                    id_=row[fields['sms_id']],
                    session_id=session.local_id,
                    session=session,
                    from_me=row[fields['type']] == TYPE_FROM_ME,
                    timestamp=self._timestamp_to_datetime(row[fields['date']]),
                    provider=self,
                    provider_data=provider_data,
                    text=row[fields['body']],
                    sender=sender,
                )

    def _timestamp_to_datetime(self, timestamp):
        # Milliseconds since the epoch
        return datetime.datetime.fromtimestamp(timestamp / 1000)

    def _find_session(self, thread_id, sender_address_id):
        # TODO: group chats
        if thread_id not in self.sessions:
            self.sessions[thread_id] = MessageSession(
                local_id=thread_id,
                provider=self,
                name='',
                participants=(self.contacts[sender_address_id],),
            )

        return self.sessions[thread_id]

    def search_contacts(self, filter_):
        return self.contacts.values()

    PII_FIELDS = {
        'sqlite3': {
            MMSSMS_DB: {
                'sms': {
                    'address': anonymise_phone,
                    'service_center': anonymise_phone,
                    'body': {anonymise_phone, anonymise_name},
                },
                'canonical_addresses': {
                    'address': anonymise_phone,
                },
                'threads': {
                    'snippet': {anonymise_phone, anonymise_name},
                },
            }
        }
    }

    def subset(self, subsetter, events, contacts):
        """
        Create a subset using the given events and contacts.
        """
        with self._db() as conn:
            with subsetter.db_subset(src_conn=conn, new_db_pathname=self.MMSSMS_DB) as subset_db:
                rows_sms = subset_db.row_subset("sms", "_id")
                rows_threads = subset_db.row_subset('threads', '_id')
                rows_address = subset_db.row_subset('canonical_addresses', '_id')

                rows_address.update(
                    contact.local_id for contact in contacts if contact.providerName == self.NAME
                )
                rows_threads.update(
                    event.provider_data.threads_table_id for event in events if event.provider.NAME == self.NAME
                )
                rows_sms.update(event.id_ for event in events if event.provider.NAME == self.NAME)

    def all_files(self):
        # TODO
        return []

    @classmethod
    def from_filesystem(cls, fs):
        """
        Return a class instance if the provider recognises data on this filesystem, None if not.
        """
        return cls(fs) if fs.exists(cls.MMSSMS_DB) else None

    # LazyContactProvider interface
    def contact_load_all(self):
        # We don't really have a list of contacts.
        address_table = Table('canonical_addresses')
        query = Query\
            .from_(address_table)\
            .select(address_table._id, address_table.address)

        with self._db() as conn:
            for row in conn.execute(query.get_sql()):
                yield {'_id': str(row[0]), 'address': row[1]}

    def contact_create(self, _id, address):
        return Contact(
            local_id=_id,
            device_id=self.fs.id_,
            name=Name(display=address),
            providerName=self.NAME,
            providerFriendlyName=self.FRIENDLY_NAME,
            provider_data=None,
            phone=address,
        )

    def contact_unknown(self, local_id):
        return None

    def get_media(self, local_id):
        """
        Return the pathname, relative to the filesystem, of media identified by 'local_id'.
        """
        raise NotImplementedError()
