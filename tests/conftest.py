import json
import os
import os.path
import subprocess
import time
import urllib.request

import pytest

PYTHON = os.environ.get('PYTHON', 'python3.10')
RIME_PORT = int(os.environ.get('RIME_PORT', '5001'))
RIME_HOST = os.environ.get('RIME_HOST', 'localhost')
RIME_METHOD = os.environ.get('RIME_METHOD', 'http')

VENV = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, '.venv'))

RIMESERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
RIMESERVER_CMD = [os.path.join(VENV, 'bin', 'uvicorn'), '--interface', 'asgi3', '--port', str(RIME_PORT),
                  '--factory', 'rime:rimeserver_create_app']
RIMESERVER_ENV = {
    'RIME_CONFIG': os.path.join(RIMESERVER_DIR, 'frontend', 'rime_settings.yaml'),
}


def _rime_server_running(timeout=0):
    # Check if we can connect to the RIME server.
    stop_trying = time.time() + timeout

    while True:
        try:
            pong_str = urllib.request.urlopen(f'{RIME_METHOD}://{RIME_HOST}:{RIME_PORT}/ping').read()
            pong = json.loads(pong_str)
            return pong['ping'] == 'pong'  # :D
        except Exception:
            if time.time() > stop_trying:
                return False

        time.sleep(0.25)


def _create_venv():
    # Create a virtual environment for the RIME server.
    if not os.path.exists(VENV):
        subprocess.run([PYTHON, '-m', 'venv', VENV], check=True)


def _install_dependencies():
    # Install the dependencies for the RIME server.
    subprocess.run([os.path.join(VENV, 'bin', 'pip'), 'install', '-r', 'requirements.txt'], check=True)


def _start_rime_server():
    # Start the RIME server in the background.
    env = os.environ.copy()
    env.update(RIMESERVER_ENV)
    return subprocess.Popen(RIMESERVER_CMD, cwd=RIMESERVER_DIR, env=env)


@pytest.fixture(scope="session", autouse=True)
def rime_server():
    " Start the RIME server (without UI) in the background, if it's not already running. "
    server_process = None

    if not _rime_server_running():
        print('RIME not running, starting a server for tests.')
        _create_venv()
        _install_dependencies()
        server_process = _start_rime_server()

    if not _rime_server_running(timeout=10):
        raise Exception('Failed to start the test-only RIME server.')

    yield

    if server_process:
        print('Terminating the test-only RIME server.')
        server_process.kill()
