from .filesystem.base import DeviceFilesystem
from .filesystem.exceptions import WrongPassphraseError
from .session import Session
from .provider import find_providers
from .errors import NotEncryptedDeviceType
from .contact import Contact, Name
from .providers.providernames import FRIENDLY_NAMES


class Device:
    def __init__(self, device_id: str, fs: DeviceFilesystem, session: Session):
        self.id_ = device_id
        self.fs = fs
        self.providers = find_providers(self.fs)
        self.session = session

        # Special contacts:

        # ... the device operator
        self.device_operator_contact = Contact(local_id='operator', device_id=self.id_, providerName='device',
                                               name=Name(display="Device operator"))

        # ... an unknown sender
        self.unknown_contact = Contact(local_id='unknown', device_id=self.id_, providerName='device',
                                       name=Name(display="Unknown"))

        # ... the device itself
        self.device_contact = Contact(local_id='device', device_id=self.id_, providerName='device',
                                      name=Name(display="System"))

        # ... individual per-device apps, created on demand.
        self._provider_contacts = {}

    def provider_contact(self, provider_name: str) -> Contact:
        if provider_name not in self._provider_contacts:
            self._provider_contacts[provider_name] = Contact(
                local_id=provider_name,
                device_id=self.id_,
                providerName=provider_name,
                providerFriendlyName=FRIENDLY_NAMES[provider_name],
                name=Name(display=FRIENDLY_NAMES[provider_name]),
            )
        return self._provider_contacts[provider_name]

    def reload_providers(self):
        self.providers = find_providers(self.fs)

    @property
    def country_code(self) -> str:
        return self.session.get_device_country_code(self.id_, 'GB')

    @country_code.setter
    def country_code(self, value: str):
        self.session.set_device_country_code(self.id_, value)

    def is_subset(self) -> bool:
        return self.fs.is_subset_filesystem()

    def is_locked(self) -> bool:
        return self.fs.is_locked()

    def lock(self, locked):
        self.fs.lock(locked)

    def is_encrypted(self) -> bool:
        return self.fs.is_encrypted()

    def device_info(self) -> str:
        try:
            return [[k,v] for (k,v) in self.fs.get_device_info().items()]
        except NotImplementedError:
            return []
    
    def decrypt(self, passphrase: str):
        """
        Try to decrypt device with provided passphrase. Return:
            - True when decryption is successful
            - False when decryption is not successful
        """

        if not self.fs.is_encrypted():
            raise NotEncryptedDeviceType(self.id_)

        try:
            self.fs.decrypt(passphrase)
            self.reload_providers()

        except WrongPassphraseError:
            print('Failed to decrypt with provided passphrase.')
            raise

    def __repr__(self):
        return f"Device({self.id_})"
