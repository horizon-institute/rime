# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

import asyncio
from collections import defaultdict
from dataclasses import dataclass
import os
import threading

from .filesystem.registry import FilesystemRegistry
from .filesystem.exceptions import WrongPassphraseError
from .session import Session
from .graphql import query as _graphql_query, query_async as _graphql_query_async
from .config import Config
from .plugins import load_plugin
from .device import Device
from .errors import NotEncryptedDeviceType, DeviceNotFound


FILESYSTEM_REGISTRY = threading.local()
DEVICE_CACHE = threading.local()
RIME = threading.local()


@dataclass(frozen=True)
class AsyncEventListener:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue


class Rime:
    """
    Top-level RIME object.

    Contains per-device sub-objects.
    """
    def __init__(self, session: Session, config: Config, enqueue_bg_call, async_loop=None):
        self.devices = []
        self.session = session
        self.config = config
        self._enqueue_bg_call = enqueue_bg_call
        media_prefix = config.get('media_url_prefix', '/media/')
        self._event_listeners_lock = threading.Lock()
        self._event_listeners = defaultdict(set[AsyncEventListener])  # event_name -> {listener, ...}
        self._events_queue = asyncio.Queue()

        self.rescan_devices()

        self.media_prefix = media_prefix
        self.plugins = self._load_plugins()

        self._file_watcher_stop_event = asyncio.Event()

        if async_loop is None:
            self.async_loop = asyncio.get_running_loop()
        else:
            self.async_loop = async_loop

        self._async_tasks = []

    def bg_call(self, fn, *args, on_complete_fn=None):
        self.async_loop.create_task(self._enqueue_bg_call(self, fn, *args, on_complete_fn=on_complete_fn))

    async def _device_list_updated_watcher(self):
        async for args in self.wait_for_events_async('device_list_updated'):
            self.rescan_devices()

    def rescan_devices(self):
        registry = FILESYSTEM_REGISTRY.registry
        registry.rescan()

        if not hasattr(DEVICE_CACHE, 'devices'):
            DEVICE_CACHE.devices = []

        new_devices = []
        old_devices = {}
        for device in DEVICE_CACHE.devices:
            if device.id_ in registry.filesystems:
                old_devices[device.id_] = device

        for device_id, fs in registry.filesystems.items():
            if device_id not in old_devices:
                device = Device(device_id, fs, self.session)
                new_devices.append(device)

        DEVICE_CACHE.devices = new_devices + list(old_devices.values())

        self.devices = DEVICE_CACHE.devices
        self._device_for_id = {device.id_: device for device in self.devices}

    # TODO: Need a synchronous version of this (or, better, a single version that can be used in both contexts)
    async def start_background_tasks_async(self):
        self._file_watcher_stop_event = asyncio.Event()

        async def watch_files_async(base_path):
            old_files = set()
            while not self._file_watcher_stop_event.is_set():
                files = set(os.listdir(base_path))
                if files != old_files:
                    old_files = files
                    self.rescan_devices()

                await asyncio.sleep(0.5)

        for async_task in (
                watch_files_async(self.filesystem_registry.base_path),
                self._event_handler(),
                self._device_list_updated_watcher()):
            self._async_tasks.append(self.async_loop.create_task(async_task))

    async def stop_background_tasks_async(self):
        self._file_watcher_stop_event.set()
        for task in self._async_tasks:
            task.cancel()

    def devices_for_ids(self, device_ids: list[str]) -> list[Device]:
        return [device for device in self.devices if device.id_ in device_ids]

    def device_for_id(self, device_id: str) -> Device:
        return self._device_for_id[device_id]

    def has_device(self, device_id: str) -> bool:
        return any(device.id_ == device_id for device in self.devices)

    def create_empty_subset_of(self, device, new_device_id, locked=True):
        if any(new_device_id == device.id_ for device in self.devices):
            raise ValueError(f"Device ID {new_device_id} already exists")

        new_fs = self.filesystem_registry.create_empty_subset_of(device.fs, new_device_id, locked=locked)
        new_device = Device(new_device_id, new_fs, self.session)
        self.devices.append(new_device)

        return new_device

    def delete_device(self, device_id: str) -> bool:
        self.filesystem_registry.delete(device_id)

        self.publish_event('device_list_updated')

        return True

    def decrypt_device(self, device_id: str, passphrase: str) -> bool:
        """
        Find if the selected device exists and then try to decrypt it
        with the provided passphrase.
        """
        # Find which of the devices tracked by RIME the passphrase is for
        target_device = None

        for device in self.devices:
            if device.id_ == device_id:
                target_device = device
                break

        if not target_device:
            raise DeviceNotFound(device_id)

        # Decrypt the device and send event on success to send new device
        # state to GraphQL subscribed clients
        try:
            target_device.decrypt(passphrase)
            self.publish_event('device_list_updated')
            return True
        except NotEncryptedDeviceType:
            return False
        except WrongPassphraseError:
            return False

    def query(self, query_json: dict):
        return _graphql_query(self, query_json)

    async def query_async(self, query_json: dict):
        return await _graphql_query_async(self, query_json)

    async def wait_for_events_async(self, event_name):
        """
        Async event subscription method.
        """
        loop = asyncio.get_running_loop()
        aqueue = asyncio.Queue()
        listener = AsyncEventListener(loop, aqueue)

        with self._event_listeners_lock:
            self._event_listeners[event_name].add(listener)

        try:
            while True:
                args = await aqueue.get()
                yield args
        finally:
            with self._event_listeners_lock:
                self._event_listeners[event_name].remove(listener)

    async def _event_handler(self):
        while True:
            event_name, args = await self._events_queue.get()

            for listener in self._event_listeners[event_name]:
                if isinstance(listener, AsyncEventListener):
                    listener.queue.put_nowait(args)
                else:
                    raise ValueError(f"Unknown event listener type {type(listener)}")

    def publish_event(self, event_name, *args):
        self._events_queue.put_nowait((event_name, args))

    def get_media(self, media_path):
        """
        Return (handle, content-type)

        where 'handle' is a file-like object representing the media, and 'content-type' is a string
        """
        device_id, provider_name, local_id = media_path.split(':', 2)

        device = self.device_for_id(device_id)
        provider = device.providers[provider_name]

        return provider.get_media(local_id)

    def get_constant(self, path: list[str], default):
        if not isinstance(path, list):
            raise ValueError("path must be a list")

        val = self.config
        for key in path[:-1]:
            if key not in val:
                return default
            val = val[key]

        return val.get(path[-1], default)

    @property
    def filesystem_registry(self) -> FilesystemRegistry:
        return FILESYSTEM_REGISTRY.registry

    @classmethod
    def create(cls, config: Config, bg_call, async_loop=None):
        if not hasattr(FILESYSTEM_REGISTRY, 'registry'):
            FILESYSTEM_REGISTRY.registry = FilesystemRegistry(
                base_path=config.get_pathname('filesystem.base_path'),
                metadata_path=config.get_pathname('metadata.base_path'),
                passphrases=config.get('filesystem').get('passphrases')
            )

        session = Session(config.get_pathname('session.database'))
        obj = cls(session, config, bg_call, async_loop=async_loop)

        return obj

    def _load_plugins(self):
        plugins = {}
        for category, plugin_list in self.config.get('plugins', {}).items():
            if not plugin_list:
                continue

            plugins[category] = []
            for plugin_name in plugin_list:
                plugins[category].append(load_plugin(category, plugin_name))

        return plugins
