import os.path
import pathlib

from yaml import load as load_yaml, Loader


class Config:
    """
    Global configuration for RIME using a YAML file.
    """
    def __init__(self, yaml, base_path='./'):
        self.yaml = yaml
        self.base_path = base_path

    @classmethod
    def from_file(cls, filename):
        with open(filename) as h:
            config = load_yaml(h, Loader=Loader)

        base_path = os.path.abspath(os.path.dirname(filename))
        return cls(config, base_path)

    def __getitem__(self, key):
        return self.yaml[key]

    def get(self, key, default=None):
        return self.yaml.get(key, default)

    def get_pathname(self, key):
        val = self.yaml
        for keypart in key.split('.'):
            val = val[keypart]

        val = pathlib.PurePosixPath(val)

        return pathlib.Path(self.base_path) / val
