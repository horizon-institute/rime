import asyncio
import builtins
import os
import sys
import shutil
import zipfile

# Try to find the Python dir using the first element of sys.path.
PYTHONDIR = os.path.dirname(sys.path[0])

# Poor man's python._pth:
sys.path.append(os.path.join(PYTHONDIR, "site-packages.zip"))
sys.path.append(os.path.join(PYTHONDIR, "Lib", "site-packages"))
sys.path.append(os.path.join(PYTHONDIR, "rime.whl"))
sys.path.append(os.path.join(PYTHONDIR, "pyd"))
sys.path.append(PYTHONDIR)

import uvicorn

# Determine a configuration location based on operating system.
if sys.platform == 'win32':
    appdata = os.environ.get('APPDATA', os.path.expanduser('~/AppData/Local'))
    rime_base = os.path.join(appdata, 'RIME')
elif sys.platform == 'darwin':
    rime_base = os.path.expanduser('~/Library/Application Support/RIME')
else:
    rime_base = os.path.expanduser('~/.rime')

os.makedirs(rime_base, exist_ok=True)

# Monkey-patch pycryptodome to also check the Lib/site-packages/Crypto in the Python installation for .pyd (native library)
# files. This is because site-packages is zipped, but native code can't be zip imported, so .pyd files are stored
# separate to the archive.

from Crypto.Util import _raw_api

_pycryptodome_filename_orig = _raw_api.pycryptodome_filename

def pycryptodome_filename(dir_comps, filename):
    if filename.endswith('.pyd'):
        full_pathname = os.path.join(PYTHONDIR, 'Lib', 'site-packages', *dir_comps, filename)
        if os.path.exists(full_pathname):
            return full_pathname
            
    return _pycryptodome_filename_orig(dir_comps, filename)
    
_raw_api.pycryptodome_filename = pycryptodome_filename

# Monkey-patch Ariadne to load HTML files from the frontend ZIP file.
_orig_open = builtins.open
def open_with_zip(filename, mode='r', *args, **kw):
    if 'site-packages.zip\\' in filename and mode == 'r':
        pathname_in_zip = filename.split('site-packages.zip\\')[1]
        pathname_in_zip = pathname_in_zip.replace('\\', '/')
        
        class Reader:
            def __init__(self, zf):
                self.zf = zf

            def read(self):
                data = self.zf.read(pathname_in_zip)
                if mode == 'r':
                    data = data.decode(kw.get('encoding'))
                    
                return data

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.zf.close()
        
        return Reader(zipfile.ZipFile(os.path.join(PYTHONDIR, 'site-packages.zip'), 'r'))

    return _orig_open(filename, mode, *args, **kw)

builtins.open = open_with_zip
# This import is not unused: importing apollo calls open_with_zip as a side effect.
import ariadne.explorer.apollo
builtins.open = _orig_open

# Locate the config, copying a template if it doesn't exist.
config_pathname = os.path.join(rime_base, 'rime_settings.yaml')
if not os.path.exists(config_pathname):
    config_dist_pathname = os.path.join(PYTHONDIR, 'rime_settings.dist.yaml')
    shutil.copy(config_dist_pathname, config_pathname)

    # Since we created the config, this may be a new install. Copy the examples as well.
    examples_dist_dir = os.path.join(PYTHONDIR, 'example')
    examples_dir = os.path.join(rime_base, 'example')
    shutil.copytree(examples_dist_dir, examples_dir)

# Locate the frontend ZIP file.
frontend_zip_pathname = os.path.join(PYTHONDIR, 'frontend.zip')

# The schema is in the same place.
schema_pathname = os.path.join(PYTHONDIR, 'schema.graphql')

# Run RIME via Uvicorn. The late import is because we rely on the above monkey-patches.
from rime import rimeserver_create_app

# Create an event loop for both Uvicorn and RIME..
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

async def create_app():
    return rimeserver_create_app(
        config_pathname=config_pathname,
        frontend_zip_pathname=frontend_zip_pathname,
        schema_pathname=schema_pathname)

app = loop.run_until_complete(create_app())

uvicorn.run(app, host='localhost', port=3000)
