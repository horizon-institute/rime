"""
Convenience script to let RIME users start the RIME server by running `python -m rime`.
"""
import os
import sys
import subprocess


CMDLINE = [
    sys.executable,
    '-m',
    'uvicorn',
    '--interface',
    'asgi3',
    '--factory',
    'rime:rimeserver_create_app',
    '--port',
    '5001',
]


CONFIG_TEMPLATE = """ # Auto-generated RIME configuration file
filesystem:
  base_path: "{filesystem_base}"
metadata:
  base_path: "{metadata_base}"
session:
  database: "{session_pathname}"
media_url_prefix: "http://localhost:5001/media/"
plugins:
  anonymise:
"""


def get_rime_base():
    """
    """
    if 'RIME_BASE' in os.environ:
        return os.environ['RIME_BASE']

    # Create a per-application configuration directory.
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', os.path.expanduser('~/AppData/Roaming'))
        rime_base = os.path.join(appdata, 'RIME')
    elif sys.platform == 'darwin':
        rime_base = os.path.expanduser('~/Library/Application Support/RIME')
    else:
        rime_base = os.path.expanduser('~/.rime')

    os.makedirs(rime_base, exist_ok=True)

    return rime_base


def get_rime_config():
    """
    """
    rime_base = get_rime_base()
    rime_config = os.path.join(rime_base, 'rime_settings.yaml')

    if not os.path.exists(rime_config):
        # Create a default config file.
        config_vars = {
            'filesystem_base': os.path.join(rime_base, 'example'),
            'metadata_base': os.path.join(rime_base, 'metadata'),
            'session_pathname': os.path.join(rime_base, 'rime_session.db'),
        }
        with open(rime_config, 'w') as h:
            h.write(CONFIG_TEMPLATE.format(**config_vars))

        os.makedirs(config_vars['filesystem_base'], exist_ok=True)
        os.makedirs(config_vars['metadata_base'], exist_ok=True)

    return rime_config


def main():
    env = os.environ.copy()
    env['RIME_CONFIG'] = get_rime_config()

    subprocess.run(CMDLINE, env=env)


main()

