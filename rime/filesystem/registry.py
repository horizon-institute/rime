import os
import re
from logging import getLogger
import shutil

from .base import DeviceFilesystem
from .android import AndroidDeviceFilesystem, AndroidZippedDeviceFilesystem
from .ios import IosDeviceFilesystem, IosZippedDeviceFilesystem, IosEncryptedDeviceFilesystem


log = getLogger(__name__)

VALID_DEVICE_ID_REGEX = re.compile(r'^[a-zA-Z0-9_-]+$')


FILESYSTEM_TYPES = {
    AndroidDeviceFilesystem,
    AndroidZippedDeviceFilesystem,
    IosDeviceFilesystem,
    IosZippedDeviceFilesystem,
    IosEncryptedDeviceFilesystem,
}


class FilesystemRegistry:
    """
    Maintains a registry of filesystems at 'base_path'.

    Filesystems are distinguished by a key, which is the name of the directory they're in under base_path.
    """
    def __init__(self, base_path, passphrases):
        self.base_path = base_path
        self.passphrases = passphrases
        self.filesystems = self._find_available_filesystems()  # maps key to FS object.

    def __getitem__(self, key):
        return self.filesystems[key]

    def rescan(self):
        self.filesystems = self._find_available_filesystems()

    def _find_available_filesystems(self):
        """
        Return a mapping of key -> filesystem type for each valid filesystem under base_path.
        """
        filesystems = {}

        try:
            for filename in os.listdir(self.base_path):
                path = os.path.join(self.base_path, filename)

                for fs_cls in FILESYSTEM_TYPES:
                    if fs_cls.is_device_filesystem(path):
                        filesystems[filename] = fs_cls(filename, path)

                        # If the FileSystem is encrypted and there is
                        # a passphrase provided as part of the YAML configuration
                        # (probably in `rime_settings.yaml`) then decrypt it
                        if (('Encrypted' in fs_cls.__name__)
                                and self.passphrases
                                and (filename in self.passphrases)):
                            filesystems[filename].decrypt(self.passphrases[filename])

        except FileNotFoundError:
            log.warning(f"Could not find filesystem directory: {self.base_path}")

        return filesystems

    def create_empty_subset_of(self, fs: DeviceFilesystem, key: str, locked: bool = False) -> DeviceFilesystem:
        """
        Create an empty subset filesystem of the same type as 'fs' named 'key'
        """
        path = os.path.join(self.base_path, key)

        if os.path.exists(path):
            raise FileExistsError(key)

        if not self.is_valid_device_id(key):
            raise ValueError(f"Invalid device ID: {key}")

        self.filesystems[key] = fs.__class__.create(key, path, template=fs)
        self.filesystems[key].lock(locked)

        return self[key]

    def is_valid_device_id(self, key):
        return VALID_DEVICE_ID_REGEX.match(key)

    def delete(self, key):
        if key not in self.filesystems:
            raise FileNotFoundError(key)

        shutil.rmtree(os.path.join(self.base_path, key))
        del self.filesystems[key]
