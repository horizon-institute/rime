# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

"""
Support for GraphQL querying in RIME.
"""
import asyncio
import logging
import re
import traceback
from dataclasses import dataclass

from datetime import datetime
from pathlib import Path

from ariadne import ObjectType, QueryType, InterfaceType, MutationType, \
                    load_schema_from_path, make_executable_schema, graphql_sync, ScalarType, graphql as graphql_async,\
                    SubscriptionType, subscribe as _ariadne_subscribe_async

from .filter import EventsFilter, ContactsFilter, ProvidersFilter, TheAlwaysMatchesPattern, GlobalContactId
from .event import MessageEvent, MediaEvent
from .mergedcontact import merge_contacts
from .anonymise import Anonymiser
from .subset import DeviceSubsetter, ProviderSubsetter, SubsetOptions, SubsetFillOption
from .device import Device
from .provider import Provider
from .event import Event, MessageSession

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# A per-query context which includes RIME. This is what is provided in the per-query context value.
class QueryContext:
    def __init__(self, rime):
        self.rime = rime


# Convert DateTime objects to ISO strings. (ref https://ariadnegraphql.org/docs/scalars)
datetime_scalar = ScalarType('DateTime')


@datetime_scalar.serializer
def serialize_datetime(value):
    return value.isoformat()


@datetime_scalar.value_parser
def parse_datetime(value):
    return datetime.fromisoformat(value)


@dataclass
class ContactsResult:
    contacts: list
    mergedContacts: list


# Resolving Query commands and producing Events.

query_resolver = QueryType()


def _make_events_filter(events_filter):
    if events_filter:
        type_names = events_filter.get('typeNames')

        provider_names = events_filter.get('providerNames')

        # Convert global contact IDs to filterable contact IDs (basically providerName, local ID).
        participant_id_strings = events_filter.get('participantIds')
        participant_ids = [GlobalContactId.from_string(s) for s in participant_id_strings] \
            if participant_id_strings \
            else []

        return EventsFilter(
            participant_ids=participant_ids,
            timestamp_start=events_filter.get('timestampStart'),
            timestamp_end=events_filter.get('timestampEnd'),
            type_names=set(type_names) if type_names is not None else None,
            provider_names=set(provider_names) if provider_names is not None else None,
        )

    return EventsFilter.empty()


def _make_contacts_filter(contacts_filter):
    if contacts_filter:
        name_regex_str = contacts_filter.get('nameRegex')

        return ContactsFilter(
            name_regex=re.compile(name_regex_str) if name_regex_str else TheAlwaysMatchesPattern,
        )

    return ContactsFilter.empty()


def _make_providers_filter(providers_filter):
    if providers_filter:
        name_regex = re.compile(providers_filter.get('nameRegex')) \
            if providers_filter.get('nameRegex') \
            else TheAlwaysMatchesPattern

        return ProvidersFilter(
            name_regex=name_regex,
        )

    return ProvidersFilter.empty()


@dataclass
class EventsByProvider:
    device: Device
    provider: Provider
    events: list[Event]
    message_sessions: list[MessageSession]

    @classmethod
    def for_devices(cls, devices, filter_obj):
        for device in devices:
            for provider in device.providers.values():
                provider_events = filter_obj.apply(provider.search_events(device, filter_obj))
                provider_message_sessions = []

                # Set session global IDs here as we add them, and update the event session ID.
                for event in provider_events:
                    if isinstance(event, MessageEvent) and event.session is not None:
                        event.session.global_id = f'{device.id_}:{provider.NAME}:{event.session.local_id}'
                        event.session_id = event.session.global_id
                        provider_message_sessions.append(event.session)

                # Decorate provider_events with the device ID as resolvers below this one need it.
                for event in provider_events:
                    event.device_id = device.id_

                yield cls(device, provider, provider_events, provider_message_sessions)


@query_resolver.field('events')
def resolve_events(parent, info, deviceIds, filter=None):
    rime = info.context.rime
    filter_obj = _make_events_filter(filter)
    devices = rime.devices_for_ids(deviceIds)

    events = []
    device_ids = set()
    providers = set()
    seen_providers = set()
    message_sessions = set()
    for ebp in EventsByProvider.for_devices(devices, filter_obj):
        device_ids.add(ebp.device.id_)
        if ebp.provider.NAME not in seen_providers:
            providers.add(ebp.provider)
            seen_providers.add(ebp.provider.NAME)
        events.extend(ebp.events)
        message_sessions.update(ebp.message_sessions)

    device_ids = list(device_ids)
    device_ids.sort()
    events.sort(key=lambda e: (e.timestamp, e.device_id))

    return {'deviceIds': device_ids, 'providers': providers, 'events': events,
            'messageSessions': message_sessions}


events_result_resolver = ObjectType('EventsResult')


@events_result_resolver.field('messageSessions')
def resolve_message_sessions(events_result, info):
    return events_result['messageSessions']


event_resolver = InterfaceType('Event')


@event_resolver.field('id')
def resolve_event_id(event, info):
    return event.id_


@event_resolver.type_resolver
def resolve_event_type(obj, *_):
    if isinstance(obj, MessageEvent):
        return 'MessageEvent'
    elif isinstance(obj, MediaEvent):
        return 'MediaEvent'
    raise TypeError(f'Unknown event type: {obj}')


# Resolvers common to all event types
def _event_resolve_timestamp(event, info):
    return event.timestamp


def _event_resolve_provider_name(event, info):
    return event.provider.NAME


def _event_resolve_provider_friendly_name(event, info):
    return event.provider.FRIENDLY_NAME


def _event_resolve_message_event_device_id(event, info):
    return event.provider.fs.id_


def _event_resolve_generic_event_info(event, info):
    if event.generic_event_info is not None:
        return {
            'category': event.generic_event_info.category,
            'isUserGenerated': event.generic_event_info.is_user_generated
        }


message_event_resolver = ObjectType('MessageEvent')


message_event_resolver.set_field('timestamp', _event_resolve_timestamp)
message_event_resolver.set_field('providerName', _event_resolve_provider_name)
message_event_resolver.set_field('providerFriendlyName', _event_resolve_provider_friendly_name)
message_event_resolver.set_field('deviceId', _event_resolve_message_event_device_id)
message_event_resolver.set_field('genericEventInfo', _event_resolve_generic_event_info)


@message_event_resolver.field('fromMe')
def resolve_from_me(event, info):
    return event.from_me


@message_event_resolver.field('text')
def resolve_text(event, info):
    return event.text


@message_event_resolver.field('sessionId')
def resolve_session_id(event, info):
    return event.session_id


@message_event_resolver.field('sender')
def resolve_sender(event, info):
    return event.sender


def _media_local_id_to_url(rime, device_id, provider_name, local_id):
    return f'{rime.media_prefix}{device_id}:{provider_name}:{local_id}'


@message_event_resolver.field('media')
def resolve_media(event, info):
    if event.media is None:
        return None

    # Convert local_id to URL.
    url = _media_local_id_to_url(info.context.rime, event.device_id, event.provider.NAME, event.media.local_id)

    return {'mime_type': event.media.mime_type, 'url': url}


# Message sessions


message_session_resolver = ObjectType('MessageSession')


@message_session_resolver.field('sessionId')
def resolve_message_session_id(session, info):
    return session.global_id


@message_session_resolver.field('providerName')
def resolve_message_session_provider_name(session, info):
    return session.provider.NAME


@message_session_resolver.field('providerFriendlyName')
def resolve_message_session_provider_friendly_name(session, info):
    return session.provider.FRIENDLY_NAME


# Media events


media_event_resolver = ObjectType('MediaEvent')

media_event_resolver.set_field('timestamp', _event_resolve_timestamp)
media_event_resolver.set_field('providerName', _event_resolve_provider_name)
media_event_resolver.set_field('providerFriendlyName', _event_resolve_provider_friendly_name)
media_event_resolver.set_field('deviceId', _event_resolve_message_event_device_id)
media_event_resolver.set_field('genericEventInfo', _event_resolve_generic_event_info)


@media_event_resolver.field('url')
def resolve_media_event_url(event, info):
    return _media_local_id_to_url(info.context.rime, event.device_id, event.provider.NAME, event.local_id)


# And Providers


provider_resolver = ObjectType('Provider')


@query_resolver.field('providers')
def resolve_providers(parent, info, deviceId, filter=None):
    filter_obj = _make_providers_filter(filter)
    rime = info.context.rime

    devices = rime.devices_for_ids([deviceId])

    providers = []
    added_providers = set()

    for device in devices:
        for provider in device.providers.values():
            if filter_obj.name_regex.search(provider.NAME) and provider.NAME not in added_providers:
                providers.append(provider)
                added_providers.add(provider.NAME)

    return providers


@provider_resolver.field('name')
def resolve_providerName(provider, info):
    return provider.NAME


@provider_resolver.field('friendlyName')
def resolve_providerFriendlyName(provider, info):
    return provider.FRIENDLY_NAME


@provider_resolver.field('id')
def resolve_id(provider, info):
    return provider.NAME  # We just use the same NAME field for now


@provider_resolver.field('deviceId')
def resolve_providerDevice(provider, info):
    return provider.fs.id_


# And Contacts

name_resolver = ObjectType('Name')


@name_resolver.field('first')
def resolve_name_first(name, info):
    return name.first


@name_resolver.field('last')
def resolve_name_last(name, info):
    return name.last


@name_resolver.field('display')
def resolve_name_display(name, info):
    return name.display


contact_resolver = ObjectType('Contact')


def _get_contacts_by_provider(rime, devices, filter_obj):
    for device in devices:
        for provider in device.providers.values():
            yield (provider, filter_obj.apply(provider.search_contacts(filter_obj)))


@query_resolver.field('contacts')
def resolve_contacts(parent, info, deviceIds, filter=None):
    filter_obj = _make_contacts_filter(filter)
    rime = info.context.rime
    devices = rime.devices_for_ids(deviceIds)

    all_contacts = []
    for provider, contacts in _get_contacts_by_provider(rime, devices, filter_obj):
        all_contacts.extend(contacts)

    merged_contacts = merge_contacts(rime, all_contacts)

    return ContactsResult(contacts=all_contacts, mergedContacts=merged_contacts)


@contact_resolver.field('id')
def resolve_contact_id(contact, info):
    # Convert the contact local ID into a device-global ID by prepending the provider name.
    return GlobalContactId.make_global_id_str(contact)


@contact_resolver.field('deviceId')
def resolve_contact_deviceId(contact, info):
    return contact.device_id


@contact_resolver.field('name')
def resolve_contact_contactName(contact, info):
    return contact.name


@contact_resolver.field('providerName')
def resolve_contact_providerName(contact, info):
    return contact.providerName


@contact_resolver.field('providerFriendlyName')
def resolve_contact_providerFriendlyName(contact, info):
    return contact.providerFriendlyName


@contact_resolver.field('email')
def resolve_contact_email(contact, info):
    return contact.email


@contact_resolver.field('phone')
def resolve_contact_phone(contact, info):
    return contact.phone


merged_contact_resolver = ObjectType('MergedContact')


@merged_contact_resolver.field('id')
def resolve_merged_contact_id(merged_contact, info):
    return f'merged:merged:{merged_contact.local_id}'


@merged_contact_resolver.field('mergedIds')
def resolve_merged_contact_mergedIds(merged_contact, info):
    return [GlobalContactId.make_global_id_str(contact) for contact in merged_contact.contacts]


# Devices
device_resolver = ObjectType('Device')


@query_resolver.field('devices')
def resolve_devices(parent, info):
    rime = info.context.rime
    return rime.devices


@device_resolver.field('id')
def resolve_device_id(device, info):
    return device.id_


@device_resolver.field('is_subset')
def resolve_device_is_subset(device, info):
    return device.is_subset()


@device_resolver.field('is_locked')
def resolve_device_is_locked(device, info):
    return device.is_locked()


@device_resolver.field('is_encrypted')
def resolve_device_is_encrypted(device, info):
    return device.is_encrypted()


@device_resolver.field('country_code')
def resolve_device_country_code(device, info):
    return device.country_code

# Device Info is a set of key/value pairs
class DeviceInfoItem:
    def __init__(self, key, value):
        self.key = key
        self.value = value

@device_resolver.field('device_info')
def resolve_device_info(device, info):
    return [DeviceInfoItem(k,v) for (k,v) in device.device_info()]


device_info_item_resolver = ObjectType('DeviceInfoItem')

@device_info_item_resolver.field('key')
def resolve_device_info_key(device_info_item, info):
    return device_info_item.key


@device_info_item_resolver.field('value')
def resolve_device_info_value(device_info_item, info):
    return device_info_item.value

# Subsetting


# Represents the class of errors we can expect callers to manage.
class CreateSubsetError(Exception):
    """
    Error occurred while creating a subset.
    """
    ERR_NONE = 0
    ERR_NAME_EXISTS = 1
    ERR_NAME_INVALID = 2
    ERR_UNKNOWN = 3

    def __init__(self, msg, code):
        super().__init__(msg)
        self.code = code


def _create_subset_prepare_device(rime, target):
    device_id = target['oldDeviceId']
    new_device_id = target['newDeviceId']

    device = rime.device_for_id(device_id)

    # Create the subsetted device.
    if rime.has_device(new_device_id):
        raise CreateSubsetError(f'Device with id {new_device_id} already exists', CreateSubsetError.ERR_NAME_EXISTS)

    if not rime.filesystem_registry.is_valid_device_id(new_device_id):
        raise CreateSubsetError(f'Invalid device id {new_device_id}', CreateSubsetError.ERR_NAME_INVALID)

    new_device = rime.create_empty_subset_of(device, new_device_id, locked=True)

    return device, new_device


def _create_subset_populate_device(rime, opts: SubsetOptions, device, new_device, events_filter_obj,
                                   contacts_filter_obj):
    """
    Create a subset of 'targets' with events and contacts matching the supplied filters.

    Returns the new Device object.

    Raises CreateSubsetError for any error we might expect callers to reasonably deal with.
    May raise anything else if something goes wrong (e.g. while a particular provider is perfoming a subset).
    """
    device_subsetter = DeviceSubsetter(new_device.fs, opts)

    # Find and remember the contacts subset.
    contacts_by_provider = {
        provider.NAME: contacts
        for provider, contacts
        in _get_contacts_by_provider(rime, [device], contacts_filter_obj)
    }

    # Create the subset of events.
    unsubsetted_contact_providers = set(contacts_by_provider.keys())
    for ebp in EventsByProvider.for_devices([device], events_filter_obj):
        if ebp.provider.NAME in contacts_by_provider:
            unsubsetted_contact_providers.remove(ebp.provider.NAME)
            contacts_for_provider = contacts_by_provider[ebp.provider.NAME]
        else:
            contacts_for_provider = []

        provider_subsetter = ProviderSubsetter(device_subsetter, opts)

        ebp.provider.subset(provider_subsetter, ebp.events, contacts_for_provider)

    # Also subset contacts-only providers with no subsetted events.
    for provider_name in unsubsetted_contact_providers:
        provider = device.providers[provider_name]

        provider_subsetter = ProviderSubsetter(device_subsetter, opts)
        provider.subset(provider_subsetter, [], contacts_by_provider[provider_name])

    new_device.reload_providers()

    return new_device


mutation = MutationType()


async def _create_subset_impl(rime, targets, eventsFilter, contactsFilter, anonymise):
    # TODO: status updates
    devices = []  # list of (old device, new device)
    new_device_ids = []

    # Create default subset options. TODO: Expose these to GraphQL.
    opts = SubsetOptions(
        fill=SubsetFillOption.UNUSED_DBS_AND_TABLES,
        anonymise=anonymise,
    )

    anonymiser = Anonymiser(rime) if anonymise else None
    events_filter_obj = _make_events_filter(eventsFilter)
    contacts_filter_obj = _make_contacts_filter(contactsFilter)

    success = False

    for target in targets:
        old_device, new_device = _create_subset_prepare_device(rime, target)
        devices.append((old_device, new_device))

    try:
        for old_device, new_device in devices:
            _create_subset_populate_device(rime, opts, old_device, new_device, events_filter_obj,
                                           contacts_filter_obj)
            if anonymiser:
                for provider in new_device.providers.values():
                    anonymiser.anonymise_device_provider(new_device, provider)
            new_device.lock(False)
            new_device_ids.append(new_device.id_)
        success = True
    finally:
        # Remove partially-created but -failed clones.
        if not success:
            for old_device, new_device in devices:
                rime.delete_device(new_device.id_)

    # Rescan our own device list.
    rime.rescan_devices()

    return new_device_ids


async def _create_subset_complete(rime, new_device_ids, exc):
    # Callback when the subset task finishes.
    if exc:
        rime.publish_event('subset_complete', {
            'success': False,
            'deviceIds': [],
            'errorMessage': str(exc),
            'errorCode': exc.code if isinstance(exc, CreateSubsetError) else CreateSubsetError.ERR_UNKNOWN,
        })
    else:
        rime.publish_event('subset_complete', {
            'success': True,
            'deviceIds': new_device_ids,
            'errorMessage': None,
            'errorCode': 0,
        })

    rime.publish_event('device_list_updated')


@mutation.field('createSubset')
def resolve_create_subset(rime, info, targets, eventsFilter, contactsFilter, anonymise):
    rime = info.context.rime
    rime.bg_call(_create_subset_impl, targets, eventsFilter, contactsFilter, anonymise, on_complete_fn=_create_subset_complete)

    return True


@mutation.field('deleteDevice')
def resolve_delete_device(rime, info, deviceId):
    return info.context.rime.delete_device(deviceId)


@mutation.field('decryptDevice')
def resolve_decrypt_device(_, info, deviceId: str, passphrase: str):
    print(f'deviceId: {deviceId}, passphrase: {passphrase}')
    info.context.rime.decrypt_device(deviceId, passphrase)


@mutation.field('setDeviceProperties')
def resolve_set_device_properties(rime, info, deviceId, deviceProperties):
    if not (deviceId and deviceProperties):
        return False

    device = info.context.rime.device_for_id(deviceId)

    if device_id := deviceProperties.get('id'):
        device.id_ = device_id

    if country_code := deviceProperties.get('countryCode'):
        device.country_code = country_code

    return True


# Subscriptions
devices_subscription = SubscriptionType()


@devices_subscription.source("devicesChanged")
async def devices_generator(obj, info):
    rime = info.context.rime

    yield rime.devices

    async for evt in rime.wait_for_events_async('device_list_updated'):
        yield rime.devices
        await asyncio.sleep(0.1)


@devices_subscription.field("devicesChanged")
def devices_resolver(payload, info):
    return payload


subsets_subscription = SubscriptionType()


@subsets_subscription.source("subsetComplete")
async def subsets_generator(obj, info):
    rime = info.context.rime

    async for subsetResult in rime.wait_for_events_async('subset_complete'):
        yield subsetResult
        await asyncio.sleep(0.1)


@subsets_subscription.field("subsetComplete")
def subsets_resolver(payload, info):
    return payload


RESOLVERS = [
    datetime_scalar, query_resolver, event_resolver, message_event_resolver, media_event_resolver,
    message_session_resolver, provider_resolver, contact_resolver, merged_contact_resolver, name_resolver,
    device_resolver, device_info_item_resolver,
    mutation, devices_subscription, subsets_subscription, events_result_resolver
]


schema = None


def load_schema(schema_pathname: Path|None = None):
    """
    Load the schema from disk. Must be invoked before GraphQL is used.
    """
    global schema

    if schema_pathname is None:
        schema_pathname = Path(__file__).parent / 'schema.graphql'

    schema_txt = load_schema_from_path(str(schema_pathname))

    schema = make_executable_schema(schema_txt, *RESOLVERS)
    return schema


# Querying
def query(rime, query_json):
    context = QueryContext(rime)
    return graphql_sync(schema, query_json, context_value=context)


async def query_async(rime, query_json):
    context = QueryContext(rime)
    return await graphql_async(schema, query_json, context_value=context)


async def subscribe_async(rime, query_json):
    context = QueryContext(rime)
    return await _ariadne_subscribe_async(schema, query_json, context_value=context)
