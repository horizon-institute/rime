# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

from dataclasses import dataclass
import datetime

from ..provider import Provider
from ..sql import Table, Query, get_field_indices
from ..event import MessageEvent, MessageSession
from ..contact import Contact, Name
from ..anonymise import anonymise_phone, anonymise_name
from .providernames import IOS_WHATSAPP, IOS_WHATSAPP_FRIENDLY

# For the ZMESSAGETYPE column in ZWAMESSAGE
MESSAGE_TYPE_TEXT = 0

# WhatsApp iOS stores its timestamps as seconds since 1/1/2001.
WA_IOS_TS_OFFSET = 978307200


def _jid_to_phone(jid):
    if jid and '@' in jid:
        return jid.split('@')[0]
    return ''


@dataclass
class IosWhatsappMessageEvent:
    group_member: str  # ZWAMESSAGE.ZGROUPMEMBER
    chat_session_id: str


@dataclass
class IosWhatsappContact:
    chat_session_ids: list[str]  # ZWACHATSESSION.Z_PK
    profile_push_name_id: str | None  # ZWAPROFILEPUSHNAME.Z_PK
    group_member_pks: list[str]  # [ZWAZGROUPMEMBER.Z_PK]
    partner_name: str | None
    push_name: str | None


class IOSWhatsApp(Provider):
    NAME = IOS_WHATSAPP
    FRIENDLY_NAME = IOS_WHATSAPP_FRIENDLY

    CHATSTORAGE_DB = 'AppDomainGroup-group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite'

    def __init__(self, fs):
        self.fs = fs
        self.contacts = {}  # {jid: Contact}
        self._contacts_loaded = False

    def msgdb(self):
        return self.fs.sqlite3_connect(self.CHATSTORAGE_DB, read_only=True)

    @classmethod
    def from_filesystem(cls, fs):
        """
        Return a class instance if the provider recognises data on this filesystem, None if not.
        """
        return cls(fs) if fs.exists(cls.CHATSTORAGE_DB) else None

    def search_events(self, device, filter_):
        """
        Search for events matching filter_, which is an EventFilter.
        """
        if filter_ and not filter_.accepts_type('MessageEvent'):
            # We only support MessageEvents
            return []

        self._load_contacts()

        message_table = Table('ZWAMESSAGE')
        group_member_table = Table('ZWAGROUPMEMBER')

        query = Query.from_(message_table)\
            .left_join(group_member_table).on(message_table.ZGROUPMEMBER == group_member_table.Z_PK)\
            .select(message_table.Z_PK, message_table.ZTEXT, message_table.ZMESSAGEDATE, message_table.ZISFROMME,
                message_table.ZMESSAGETYPE, message_table.ZFROMJID, message_table.ZCHATSESSION,
                message_table.ZGROUPMEMBER, group_member_table.ZMEMBERJID) \
            .where(message_table.ZMESSAGETYPE == MESSAGE_TYPE_TEXT)

        fields = get_field_indices(query)

        wa_sessions = {}

        with self.msgdb() as db:
            for row in db.execute(str(query)):
                session_id = row[fields['ZCHATSESSION']]

                if session_id not in wa_sessions:
                    wa_sessions[session_id] = self._create_session(session_id)

                if row[fields['ZISFROMME']] == 1:
                    sender_jid = None
                elif row[fields['ZGROUPMEMBER']] is not None:
                    # In group chats, ZFROMJID is the group JID, and the sender is found in the
                    # ZWAGROUPMEMBER table.
                    sender_jid = row[fields['ZMEMBERJID']]
                else:
                    # In private chats, ZFROMJID is the sender's JID.
                    sender_jid = row[fields['ZFROMJID']]

                provider_data = IosWhatsappMessageEvent(
                    group_member=row[fields['ZGROUPMEMBER']],
                    chat_session_id=session_id
                )

                if bool(row[fields['ZISFROMME']]):
                    sender = device.device_operator_contact
                elif sender_jid:
                    sender = self._jid_to_contact(sender_jid)
                else:
                    sender = device.unknown_contact

                yield MessageEvent(
                    id_=row[fields['Z_PK']],
                    session_id=session_id,
                    session=wa_sessions[session_id],
                    timestamp=self._timestamp_to_datetime(row[fields['ZMESSAGEDATE']]),
                    provider=self,
                    provider_data=provider_data,
                    text=row[fields['ZTEXT']],
                    from_me=bool(row[fields['ZISFROMME']]),
                    sender=sender,
                )

    def search_contacts(self, filter_):
        self._load_contacts()
        return self.contacts.values()

    PII_FIELDS = {
        'sqlite3': {
            CHATSTORAGE_DB: {
                'ZWAPROFILEPUSHNAME': {
                    'ZJID': anonymise_phone,
                },
                'ZWAGROUPMEMBER': {
                    'ZMEMBERJID': anonymise_phone,
                },
                'ZWACHATSESSION': {
                    'ZCONTACTJID': anonymise_phone,
                    'ZPARTNERNAME': anonymise_phone,
                },
                'ZWAMESSAGE': {
                    'ZFROMJID': anonymise_phone,
                    'ZTOJID': anonymise_phone,
                    'ZTEXT': {anonymise_phone, anonymise_name},
                },
            }
        }
    }

    def subset(self, subsetter, events, contacts):
        """
        Create a subset using the given events and contacts.
        """
        with self.msgdb() as db:
            with subsetter.db_subset(src_conn=db, new_db_pathname=self.CHATSTORAGE_DB) as subset_db:
                rows_zwaprofilepushname = subset_db.row_subset('ZWAPROFILEPUSHNAME', 'Z_PK')
                rows_zwagroupmember = subset_db.row_subset('ZWAGROUPMEMBER', 'Z_PK')
                rows_zwachatsession = subset_db.row_subset('ZWACHATSESSION', 'Z_PK')
                rows_zwamessage = subset_db.row_subset('ZWAMESSAGE', 'Z_PK')

                # Copy the "contacts" into ZWACHATSESSION, ZWAPROFILEPUSHNAME, and ZWAGROUPMEMBER.
                for contact in contacts:
                    wa_contact = contact.provider_data

                    if wa_contact.profile_push_name_id:
                        rows_zwaprofilepushname.add(wa_contact.profile_push_name_id)

                    if wa_contact.group_member_pks:
                        rows_zwagroupmember.update(set(wa_contact.group_member_pks))

                    if wa_contact.chat_session_ids:
                        rows_zwachatsession.update(set(wa_contact.chat_session_ids))

                # Copy the events.
                for event in events:
                    wa_event = event.provider_data

                    rows_zwamessage.add(event.id_)
                    rows_zwachatsession.add(wa_event.chat_session_id)

                    if wa_event.group_member:
                        rows_zwagroupmember.add(wa_event.group_member)

    def all_files(self):
        # TODO
        return []

    def _create_session(self, session_id):
        chat_table = Table('ZWACHATSESSION')

        query = Query.from_(chat_table)\
            .select(chat_table.ZCONTACTJID, chat_table.ZPARTNERNAME, chat_table.ZGROUPINFO) \
            .where(chat_table.Z_PK == session_id)

        field_names = get_field_indices(query)

        with self.msgdb() as db:
            chat = db.execute(str(query)).fetchone()
            if not chat:
                return MessageSession(local_id=session_id, provider=self,
                                      name="Unknown wa-ios session", participants=tuple())

            if chat[field_names['ZGROUPINFO']] is not None:
                # Group chat
                group_member_table = Table('ZWAGROUPMEMBER')
                query = Query.from_(group_member_table)\
                    .select(group_member_table.ZMEMBERJID) \
                    .where(group_member_table.ZCHATSESSION == session_id)

                participants = [self._jid_to_contact(member[0]) for member in db.execute(str(query))]
            else:
                # Private chat
                participants = [self._jid_to_contact(chat[field_names['ZCONTACTJID']])]

            return MessageSession(
                local_id=session_id,
                provider=self,
                name=chat[field_names['ZPARTNERNAME']],
                participants=tuple(participants))

    def _jid_to_contact(self, jid):
        # Contacts should have been loaded already. If for some reason we encounter an unexpected JID,
        # just make something up:
        self._make_or_update_contact(jid)

        return self.contacts[jid]

    def _timestamp_to_datetime(self, timestamp):
        return datetime.datetime.fromtimestamp(WA_IOS_TS_OFFSET + float(timestamp))

    def _load_contacts(self):
        # iOS WhatsApp contacts have even less information than Android ones. We basically get the JID and
        # maybe a name.
        # Contact information is also split between ZWACHATSESSION and ZWAGROUPMEMBER. If the contact only
        # appears in group chats, it will only be in ZWAGROUPMEMBER.
        if self._contacts_loaded:
            return

        chat_table = Table('ZWACHATSESSION')
        push_name_table = Table('ZWAPROFILEPUSHNAME')

        query = Query.from_(chat_table)\
            .left_join(push_name_table)\
            .on(chat_table.ZCONTACTJID == push_name_table.ZJID)\
            .select(chat_table.Z_PK, chat_table.ZCONTACTJID, chat_table.ZPARTNERNAME, push_name_table.ZPUSHNAME,
                push_name_table.Z_PK.as_('PUSH_PK')) \
            .where(chat_table.ZCONTACTIDENTIFIER.notnull())

        field_names = get_field_indices(query)

        self.contacts = {}

        with self.msgdb() as db:
            for row in db.execute(str(query)):
                jid = row[field_names['ZCONTACTJID']]
                if jid not in self.contacts:
                    self._make_or_update_contact(
                        jid,
                        partner_name=row[field_names['ZPARTNERNAME']],
                        push_name=row[field_names['ZPUSHNAME']],
                        chat_session_id=row[field_names['Z_PK']],
                        profile_push_name_id=row[field_names['PUSH_PK']],
                    )

            # Search for missing group chat members.
            group_member_table = Table('ZWAGROUPMEMBER')
            query = Query.from_(group_member_table)\
                .left_join(push_name_table)\
                .on(group_member_table.ZMEMBERJID == push_name_table.ZJID)\
                .select(group_member_table.Z_PK, group_member_table.ZMEMBERJID, push_name_table.ZPUSHNAME,
                        push_name_table.Z_PK.as_('PUSH_PK')) \

            field_names = get_field_indices(query)

            for row in db.execute(str(query)):
                jid = row[field_names['ZMEMBERJID']]
                self._make_or_update_contact(
                    jid,
                    push_name=row[field_names['ZPUSHNAME']],
                    group_member_pk=row[field_names['Z_PK']],
                    profile_push_name_id=row[field_names['PUSH_PK']])

            self._contacts_loaded = True

    def _make_or_update_contact(self, jid, partner_name=None, push_name=None, chat_session_id=None,
            profile_push_name_id=None, group_member_pk=None):
        assert jid is not None

        if jid not in self.contacts:
            provider_data = IosWhatsappContact(
                chat_session_ids=[],
                profile_push_name_id=profile_push_name_id,
                group_member_pks=[],
                partner_name=partner_name,
                push_name=push_name
            )

            contact = Contact(
                local_id=jid,
                device_id=self.fs.id_,
                name=Name(),
                providerName=self.NAME,
                providerFriendlyName=self.FRIENDLY_NAME,
                provider_data=provider_data,
                phone=_jid_to_phone(jid)
            )

            contact.name.display = partner_name or push_name or jid

            self.contacts[jid] = contact
        else:
            contact = self.contacts[jid]

        if chat_session_id is not None:
            contact.provider_data.chat_session_ids.append(chat_session_id)

        if group_member_pk is not None:
            contact.provider_data.group_member_pks.append(group_member_pk)

    def get_media(self, local_id):
        """
        Return the pathname, relative to the filesystem, of media identified by 'local_id'.
        """
        raise NotImplementedError()
