# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

import os.path
import datetime
from typing import Iterable
from dataclasses import dataclass

from ..provider import Provider
from ..event import Event, MessageEvent, Media, MessageSession
from ..contact import Contact, Name
from ..sql import Table, Query, get_field_indices
from ..anonymise import anonymise_phone, anonymise_name
from ..media import MediaData
from .providernames import ANDROID_WHATSAPP, ANDROID_WHATSAPP_FRIENDLY

# for the message_type column in msgstore.db
MESSAGE_TYPE_TEXT = 0
MESSAGE_TYPE_IMAGE = 1
MESSAGE_TYPE_AUDIO = 2
MESSAGE_TYPE_VIDEO = 3
MESSAGE_TYPE_CONTACT = 4
MESSAGE_TYPE_LOCATION = 5
MESSAGE_TYPE_SYSTEM = 7

MEDIA_MESSAGE_TYPES = {MESSAGE_TYPE_IMAGE, MESSAGE_TYPE_AUDIO, MESSAGE_TYPE_VIDEO}

# For JID types
JID_TYPE_GROUP = 1
JID_TYPE_BROADCAST = 5
JID_TYPE_ME = 11
JID_TYPE_USER = 17


def _timestamp_to_datetime(timestamp):
    # Timestamps in whatsapp are stored as milliseconds since the epoch
    return datetime.datetime.fromtimestamp(timestamp / 1000)


def _datetime_to_timestamp(dt):
    return int(dt.timestamp() * 1000)


@dataclass
class WhatsappJid:
    """
    Whatsapp-specific info in the msgstore.db jid table.

    This is stored in WhatsappContact.jid_contacts, in a list, because there may be more than one JID row ID
    referencing a given contact.
    """
    id_: int  # jid._id
    raw_string: str  # jid.raw_string, referred to as 'jid' in wa.db.
    name: str  # jid.display_name, a phone number or group ID
    typ: int  # JID_TYPE_*


@dataclass
class WhatsappContact:
    """
    Whatsapp-specific info in the wa.db wa_contacts table.

    This goes into Contact.provider_data.
    """
    id_: int  # wa_contacts._id
    jid: str
    number: str
    display_name: str
    jid_contacts: list[WhatsappJid]

    def typ_contains(self, typ):
        return any(wa_contact.typ == typ for wa_contact in self.jid_contacts)


@dataclass
class WhatsappMessageSession:
    """
    Whatsapp-specific info for sessions.

    This goes into MessageSession.provider_data.
    """
    group_participant_user_ids: set[str]
    group_user_id: str | None
    group_jid_row_id: str | None


CONTACTS_BY_JID_ROW_ID = {}  # Maps FS ID to {jid_row_id: Contact}
CONTACTS_BY_ID = {}  # Maps FS ID to {Contact.id_: Contact}

# Group users, by filesystem ID
GROUP_USERS = {}  # Maps FS ID to {group jid: list of user jids}

# group_participant_user table indices, by filesystem ID
GROUP_PARTICIPANT_USER_IDS = {}  # Maps FS ID to {group jid: list of group participant user _id fields}


def anonymise_jid(db_anonymiser, table_name, column_name):
    return anonymise_phone(db_anonymiser, table_name, column_name)

# Extra information for message events, for recreation during subsetting.
@dataclass
class WhatsappMessageEvent:
    # Row IDs in various tables:
    message_row_id: str
    chat_row_id: str


class AndroidWhatsApp(Provider):
    NAME = ANDROID_WHATSAPP
    FRIENDLY_NAME = ANDROID_WHATSAPP_FRIENDLY

    MESSAGE_DB = 'data/data/com.whatsapp/databases/msgstore.db'  # chats
    WA_DB = 'data/data/com.whatsapp/databases/wa.db'  # contacts

    def __init__(self, fs):
        self.fs = fs
        self.msgdb = fs.sqlite3_connect(self.MESSAGE_DB, read_only=True)
        self.wadb = fs.sqlite3_connect(self.WA_DB, read_only=True)

    def __del__(self):
        self.msgdb.close()
        self.wadb.close()

    def _load_contacts(self):
        """
        Read and cache all WhatsApp contacts.
        """
        global CONTACTS_BY_JID_ROW_ID, CONTACTS_BY_ID

        if self.fs.id_ in CONTACTS_BY_JID_ROW_ID:
            return

        # First read contact information from the wa.db database.
        contacts_table = Table("wa_contacts")
        query = Query.from_(contacts_table) \
            .select("_id", "jid", "number", "display_name", "given_name", "family_name", "wa_name")

        fields = get_field_indices(query)

        contacts_by_jid = {}
        CONTACTS_BY_ID[self.fs.id_] = {}

        for row in self.wadb.execute(str(query)):
            jid = row[fields['jid']]
            wa_contact = WhatsappContact(
                id_=row[fields['_id']],
                jid=jid,
                number=row[fields['number']],
                display_name=row[fields['display_name']],
                jid_contacts=[]
            )
            new_contact = Contact(
                local_id=f'{jid}',
                device_id=self.fs.id_,
                name=Name(),
                providerName=self.NAME,
                providerFriendlyName=self.FRIENDLY_NAME,
                provider_data=wa_contact
            )
            number = row[fields['number']]
            # It's possible for number to be null, in which case we use the first part of the jid.
            if number is None:
                jid_start = jid.split('@')[0]
                number = jid_start if jid_start.startswith('+') else '+' + jid_start

            new_contact.name.first = row[fields['given_name']]
            new_contact.name.last = row[fields['family_name']]
            new_contact.name.display = row[fields['display_name']] or row[fields['wa_name']]
            new_contact.phone = number

            contacts_by_jid[jid] = new_contact
            CONTACTS_BY_ID[self.fs.id_][new_contact.local_id] = new_contact

        CONTACTS_BY_JID_ROW_ID[self.fs.id_] = {}

        jid_table = Table("jid")
        query = Query.from_(jid_table) \
            .select("_id", "user", "server", "type", "raw_string")

        fields = get_field_indices(query)

        for row in self.msgdb.execute(str(query)):
            jid = row[fields['user']] + '@' + row[fields['server']]
            contact = contacts_by_jid.get(jid, None)
            if not contact:
                # No corresponding wa_contact. But this IS mentioned in jids and MAY be referenced, so create
                # something.
                contact = Contact(
                    local_id=jid,
                    device_id=self.fs.id_,
                    name=Name(),
                    providerName=self.NAME,
                    provider_data=WhatsappContact(id_=-1, jid_contacts=[], jid=jid, number='', display_name='Unknown'),
                    phone=row[fields['user']]
                )
                contacts_by_jid[jid] = contact

            wa_jid = WhatsappJid(
                id_=row[fields['_id']],
                name=row[fields['user']],
                typ=row[fields['type']],
                raw_string=row[fields['raw_string']]
            )

            contact.provider_data.jid_contacts.append(wa_jid)

            CONTACTS_BY_JID_ROW_ID[self.fs.id_][row[fields['_id']]] = contact

    def _media_path(self, local_id):
        # TODO media is stored on the SD card, which isn't fixed.
        return f'/sdcard/WhatsApp/{local_id}'

    def get_media(self, local_id):
        # Find the content type based on the local id.
        media_table = Table('message_media')
        query = Query.from_(media_table) \
            .select('mime_type') \
            .where(media_table.file_path == local_id)

        row = self.msgdb.execute(str(query)).fetchone()
        if not row:
            raise ValueError(f'No media found for local id {local_id}')

        mime_type = row[0]

        media_path = self._media_path(local_id)

        return MediaData(
            mime_type=mime_type,
            handle=self.fs.open(media_path),
            length=self.fs.getsize(media_path),
        )

    def _get_group_contacts(self, group_jid):
        """
        Return the other users in this group.

        Excludes all non-user contacts, including JID_TYPE_ME.
        """
        self._load_contacts()

        if self.fs.id_ not in GROUP_USERS:
            GROUP_USERS[self.fs.id_] = {}

        if self.fs.id_ not in GROUP_PARTICIPANT_USER_IDS:
            GROUP_PARTICIPANT_USER_IDS[self.fs.id_] = {}

        if group_jid not in GROUP_USERS[self.fs.id_]:
            group_participant_user_table = Table('group_participant_user')
            query = Query.from_(group_participant_user_table) \
                .select('_id', 'user_jid_row_id') \
                .where(group_participant_user_table.group_jid_row_id == group_jid)

            fields = get_field_indices(query)

            GROUP_USERS[self.fs.id_][group_jid] = []
            GROUP_PARTICIPANT_USER_IDS[self.fs.id_][group_jid] = []

            for row in self.msgdb.execute(str(query)):
                GROUP_PARTICIPANT_USER_IDS[self.fs.id_][group_jid].append(row[fields['_id']])
                GROUP_USERS[self.fs.id_][group_jid].append(row[fields['user_jid_row_id']])

        contacts = []
        all_contacts = CONTACTS_BY_JID_ROW_ID[self.fs.id_]

        for jid_row_id in GROUP_USERS[self.fs.id_][group_jid]:
            if jid_row_id in all_contacts and all_contacts[jid_row_id].provider_data.typ_contains(JID_TYPE_USER):
                contacts.append(CONTACTS_BY_JID_ROW_ID[self.fs.id_][jid_row_id])

        return contacts

    def _get_contact(self, jid_row_id):
        self._load_contacts()
        return CONTACTS_BY_JID_ROW_ID[self.fs.id_].get(jid_row_id)

    def _is_group_contact(self, contact):
        return contact.provider_data.typ_contains(JID_TYPE_GROUP)

    def _create_wa_session(self, chat_id):
        chat_table = Table('chat')
        query = Query.from_(chat_table) \
            .select('jid_row_id', 'subject') \
            .where(chat_table._id == chat_id)

        fields = get_field_indices(query)

        row = self.msgdb.execute(str(query)).fetchone()
        if not row:
            return None

        jid_row_id = row[fields['jid_row_id']]
        subject = row[fields['subject']]

        contact = self._get_contact(jid_row_id)
        group_participant_user_ids = []
        group_user_id = None
        group_jid_row_id = None
        if contact:
            if self._is_group_contact(contact):
                contacts = self._get_group_contacts(jid_row_id)
                group_participant_user_ids = GROUP_PARTICIPANT_USER_IDS[self.fs.id_][jid_row_id]

                # Also add the user ID of the group itself as a participant so that subsetting includes it.
                group_user_id = contact.provider_data.id_
                group_jid_row_id = jid_row_id
            else:
                contacts = [contact]
        else:
            contacts = []

        provider_data = WhatsappMessageSession(
            group_participant_user_ids=set(group_participant_user_ids),
            group_user_id=group_user_id,
            group_jid_row_id=group_jid_row_id
        )

        return MessageSession(
            local_id=chat_id,
            provider=self,
            name=subject,
            participants=tuple(contacts),
            provider_data=provider_data
        )

    def _construct_query(self, filter_):
        # Whatsapp messages are stored in the message table:
        message_table = Table('message')
        media_table = Table('message_media')
        message_details_table = Table('message_details')
        chat_table = Table('chat')
        query = Query.from_(message_table) \
            .join(chat_table).on(chat_table._id == message_table.chat_row_id) \
            .join(message_details_table).on(message_details_table.message_row_id == message_table._id) \
            .left_join(media_table).on(media_table.message_row_id == message_table._id) \
            .select(message_table.sender_jid_row_id, message_table.message_type,
                    message_table._id, message_table.chat_row_id, message_table.text_data, message_table.timestamp,
                    message_table.from_me, message_details_table.author_device_jid,
                    media_table.file_path, media_table.mime_type,
                    ) \
            .where(message_table.message_type.isin([MESSAGE_TYPE_TEXT] + list(MEDIA_MESSAGE_TYPES)))

        # Chats are grouped by the chat_row_id column, which is a foreign key to chat._id.
        # Group chats reference a group JID which is mapped to users using the group_participant_user table.

        if filter_:
            if filter_.timestamp_start:
                query = query.where(message_table.timestamp >= _datetime_to_timestamp(filter_.timestamp_start))
            if filter_.timestamp_end:
                query = query.where(message_table.timestamp < _datetime_to_timestamp(filter_.timestamp_end))

        return query

    def search_events(self, device, filter_):
        wa_sessions = {}  # chat ID to MessageSession

        if filter_ and not filter_.accepts_type('MessageEvent'):
            # We only support MessageEvents
            return []

        query = self._construct_query(filter_)
        fields = get_field_indices(query)

        for row in self.msgdb.execute(str(query)):
            # WhatsApp's contact storage method looks like it's changed over time. The following is guesswork:
            # - If message.sender_jid_row_id is 0, its a group chat message. You can find the
            #   sender by looking at message_details.author_device_jid.
            # - If message.sender_jid_row_id is NOT 0, it's a private chat message and the sender
            #   is as indicated by sender_jid_row_id.

            # Find the sender.
            if row[fields['from_me']]:
                sender = device.device_operator_contact
            elif row[fields['sender_jid_row_id']] == 0:
                # Group chat.
                author_device_jid = row[fields['author_device_jid']]
                if author_device_jid:
                    sender = self._get_contact(author_device_jid)  # may be None
                else:
                    sender = None
            else:
                # Private chat.
                sender = self._get_contact(row[fields['sender_jid_row_id']])  # may be None

            if sender is None:
                sender = device.unknown_contact

            # Store session info.
            if row[fields['chat_row_id']] not in wa_sessions:
                wa_sessions[row[fields['chat_row_id']]] = self._create_wa_session(row[fields['chat_row_id']])

            # Store DB-specific information to re-create the database rows later if we're subsetting.
            wa_message_event = WhatsappMessageEvent(
                message_row_id=row[fields['_id']],
                chat_row_id=row[fields['chat_row_id']],
            )

            if row[fields['message_type']] in MEDIA_MESSAGE_TYPES:
                # Media message.
                media = Media(
                    mime_type=row[fields['mime_type']],
                    local_id=row[fields['file_path']])
            else:
                # Text message.
                media = None

            yield MessageEvent(
                id_=row[fields['_id']],
                session_id=str(row[fields['chat_row_id']]),
                session=wa_sessions[row[fields['chat_row_id']]],
                timestamp=_timestamp_to_datetime(row[fields['timestamp']]),
                provider=self,
                provider_data=wa_message_event,
                text=row[fields['text_data']],
                from_me=bool(row[fields['from_me']]),
                sender=sender,
                media=media,
            )

    def search_contacts(self, filter_):
        self._load_contacts()

        return [contact for contact in CONTACTS_BY_ID[self.fs.id_].values()
            if contact.provider_data.typ_contains(JID_TYPE_USER)]

    PII_FIELDS = {
        'sqlite3': {
            WA_DB: {
                'wa_contacts': {
                    'jid': anonymise_jid,
                    'number': anonymise_phone,
                    'display_name': anonymise_name,
                    'given_name': anonymise_name,
                    'family_name': anonymise_name,
                    'wa_name': anonymise_name,
                    'sort_name': anonymise_name,
                    'nickname': anonymise_name,
                },
            },
            MESSAGE_DB: {
                'jid': {
                    'user': anonymise_phone,
                    'raw_string': anonymise_phone,
                },
                'message': {
                    'text_data': {anonymise_phone, anonymise_name},
                },
            }
        }
    }

    def subset(self, subsetter, events: Iterable[Event], contacts: Iterable[Contact]):
        """
        Create a WhatsApp subset using the provided events and contacts.
        """
        # Copy the contacts
        with subsetter.db_subset(src_conn=self.wadb, new_db_pathname=self.WA_DB) as subset_wadb, \
                subsetter.db_subset(src_conn=self.msgdb, new_db_pathname=self.MESSAGE_DB) as subset_msgdb:

            rows_wa_contacts = subset_wadb.row_subset("wa_contacts", "_id")
            rows_wa_contacts.update(contact.provider_data.id_ for contact in contacts)

            # Copy session participants
            rows_group_participant_user = subset_msgdb.row_subset("group_participant_user", "_id")

            # Copy events
            rows_message = subset_msgdb.row_subset("message", "_id")
            rows_message_media = subset_msgdb.row_subset("message_media", "message_row_id")
            rows_message_details = subset_msgdb.row_subset("message_details", "message_row_id")
            rows_jid = subset_msgdb.row_subset("jid", "_id")
            rows_chat = subset_msgdb.row_subset("chat", "_id")

            for event in events:
                # Reject if it's not one of ours.
                if not isinstance(event, MessageEvent) or event.provider.NAME != self.NAME:
                    continue

                wa_message = event.provider_data

                rows_message.add(wa_message.message_row_id)
                if event.sender and event.sender.provider_data:
                    rows_jid.update(jid_contact.id_ for jid_contact in event.sender.provider_data.jid_contacts)

                if event.session:
                    wa_session = event.session.provider_data
                    rows_group_participant_user.update(wa_session.group_participant_user_ids)
                    if wa_session.group_user_id:
                        rows_wa_contacts.add(wa_session.group_user_id)
                    if wa_session.group_jid_row_id:
                        rows_jid.add(wa_session.group_jid_row_id)

                rows_message_details.add(wa_message.message_row_id)
                rows_chat.add(wa_message.chat_row_id)
                rows_message_media.add(wa_message.message_row_id)

            # copy media by copying each named file.
            media_table = Table('message_media')
            query = Query.from_(media_table) \
                .select('file_path') \
                .where(media_table.message_row_id.isin(rows_message_media.rows))

            for row in self.msgdb.execute(query.get_sql()):
                pathname = self._media_path(row[0])
                subsetter.copy_file(self.fs.open(pathname), pathname)

    def all_files(self):
        # TODO
        return []

    @classmethod
    def from_filesystem(cls, fs):
        if fs.exists(cls.MESSAGE_DB):
            return cls(fs)

        return None
