# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd
"""
Provides Apple 'Messages'
"""
import datetime
from dataclasses import dataclass
from typing import Iterable

from ..provider import Provider
from .providerutils import LazyContactProvider, LazyContactProviderContacts
from ..event import Event, MessageEvent, MessageSession
from ..contact import Contact, Name
from ..sql import Table, Query, get_field_indices
from ..anonymise import anonymise_phone, anonymise_name
from .providernames import IOS_IMESSAGE, IOS_IMESSAGE_FRIENDLY


@dataclass
class ImessageContact:
    row_id: str


@dataclass
class ImessageMessage:
    message_row_id: str
    chat_row_id: str


class IMessage(Provider, LazyContactProvider):
    NAME = IOS_IMESSAGE
    FRIENDLY_NAME = IOS_IMESSAGE_FRIENDLY

    # iOS filenames should be specified beginning DOMAIN-
    MESSAGE_DB = "HomeDomain/Library/SMS/sms.db"

    # Timestamps in imessage are (I think) stored as nanoseconds since 1/1/2001.
    # I'm guessing UTC?
    EPOCH = datetime.datetime(2001, 1, 1, 0, 0)
    EPOCH_TS = int(EPOCH.timestamp())

    def __init__(self, fs):
        self.fs = fs
        self.contacts = LazyContactProviderContacts(self)

    def _db(self):
        return self.fs.sqlite3_connect(self.MESSAGE_DB, read_only=True)

    @classmethod
    def _timestamp_to_datetime(cls, timestamp):
        return datetime.datetime.fromtimestamp(cls.EPOCH_TS + float(timestamp) / 1_000_000_000)

    @classmethod
    def _datetime_to_timestamp(cls, dt):
        return int((dt.timestamp() - cls.EPOCH_TS) * 1_000_000_000)

    def _create_session(self, chat_id):
        # Retrieve contacts
        chat_table = Table('chat')
        chat_handle_join_table = Table('chat_handle_join')
        handle_table = Table('handle')

        query = Query.from_(handle_table) \
            .join(chat_handle_join_table).on(chat_handle_join_table.handle_id == handle_table.rowid) \
            .join(chat_table).on(chat_table.rowid == chat_handle_join_table.chat_id) \
            .where(chat_table.rowid == chat_id) \
            .select('ROWID', )

        fields = get_field_indices(query)

        contacts = []
        with self._db() as conn:
            for row in conn.execute(str(query)):
                contacts.append(self.contacts[row[fields['ROWID']]])

        return MessageSession(
            local_id=chat_id,
            provider=self,
            name='',
            participants=tuple(contacts)
        )

    def search_events(self, device, filter_):
        if filter_ and not filter_.accepts_type('MessageEvent'):
            # We only support MessageEvents
            return []

        sessions = {}  # handle ID to session

        message_table = Table('message')
        chat_message_join_table = Table('chat_message_join')
        query = Query.from_(message_table) \
            .join(chat_message_join_table).on(chat_message_join_table.message_id == message_table.rowid) \
            .select('ROWID', 'guid', 'text', 'date', 'handle_id', 'is_from_me', chat_message_join_table.chat_id) \

        if filter_:
            if filter_.timestamp_start:
                query = query.where(message_table.date >= self._datetime_to_timestamp(filter_.timestamp_start))
            if filter_.timestamp_end:
                query = query.where(message_table.date < self._datetime_to_timestamp(filter_.timestamp_end))

        fields = get_field_indices(query)

        with self._db() as conn:
            for row in conn.execute(str(query)):
                chat_id = row[fields['chat_id']]
                if chat_id not in sessions:
                    sessions[chat_id] = self._create_session(chat_id)

                sender = device.device_operator_contact if row[fields['is_from_me']] else sessions[chat_id].participants[0]

                yield MessageEvent(
                    id_=row[fields['guid']],
                    session_id=chat_id,
                    session=sessions[chat_id],
                    from_me=bool(row[fields['is_from_me']]),
                    timestamp=self._timestamp_to_datetime(row[fields['date']]),
                    provider=self,
                    sender=sender,
                    provider_data=ImessageMessage(
                        message_row_id=row[fields['ROWID']],
                        chat_row_id=row[fields['chat_id']],
                    ),
                    text=row[fields['text']],
                )

    def search_contacts(self, filter_):
        return self.contacts.values()

    PII_FIELDS = {
        'sqlite3': {
            MESSAGE_DB: {
                'handle': {
                    'id': anonymise_phone,
                    'uncanonicalized_id': anonymise_phone,
                },
                'chat': {
                    'guid': anonymise_phone,
                    'chat_identifier': anonymise_phone,
                    'account_login': anonymise_phone,
                    'last_addressed_handle': anonymise_phone,
                },
                'message': {
                    'text': {anonymise_phone, anonymise_name},
                    'account': anonymise_phone,
                    'destination_caller_id': anonymise_phone,
                },
            }
        }
    }

    def subset(self, subsetter, events: Iterable[Event], contacts: Iterable[Contact]):
        """
        """
        with self._db() as conn:
            with subsetter.db_subset(src_conn=conn, new_db_pathname=self.MESSAGE_DB) as subset_db:
                handle_rows = subset_db.row_subset('handle', 'ROWID')
                handle_rows.update(
                    contact.provider_data.row_id
                    for contact in contacts
                    if contact.providerName == self.NAME
                )

                message_rows = subset_db.row_subset('message', 'ROWID')
                chat_rows = subset_db.row_subset('chat', 'ROWID')
                chat_message_join_rows = subset_db.row_subset('chat_message_join', 'chat_id')
                chat_handle_join_rows = subset_db.row_subset('chat_handle_join', 'chat_id')

                for event in events:
                    if not isinstance(event, MessageEvent) or event.provider != self:
                        continue

                    message_rows.add(event.provider_data.message_row_id)
                    chat_rows.add(event.provider_data.chat_row_id)
                    chat_message_join_rows.add(event.provider_data.chat_row_id)
                    chat_handle_join_rows.add(event.provider_data.chat_row_id)
                    if event.session:
                        handle_rows.update(contact.provider_data.row_id for contact in event.session.participants)

    def all_files(self):
        # TODO
        return []

    @classmethod
    def from_filesystem(cls, fs):
        return cls(fs) if fs.exists(cls.MESSAGE_DB) else None

    # LazyContactProvider interface
    def contact_load_all(self):
        handle_table = Table('handle')
        query = Query.from_(handle_table).select('ROWID', 'id')

        with self._db() as conn:
            for row in conn.execute(str(query)):
                yield {'rowid': str(row[0]), 'id_': row[1]}

    def contact_create(self, rowid, id_):
        return Contact(
            local_id=rowid,
            device_id=self.fs.id_,
            name=Name(),
            providerName=self.NAME,
            provider_data=ImessageContact(row_id=rowid),
            phone=id_,  # TODO: no explicit link to contacts -- need contact merging
        )

    def contact_unknown(self, local_id):
        return None

    def get_media(self, local_id):
        """
        Return the pathname, relative to the filesystem, of media identified by 'local_id'.
        """
        raise NotImplementedError()
