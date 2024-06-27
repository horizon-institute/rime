from contextlib import contextmanager
import os
import secrets
import shutil
import tempfile
import time
from zipfile import ZipFile, Path, ZipInfo

def get_zipfile_main_dir(zf: ZipFile) -> Path:
    """
    Zipped filesystem support assumes that there is one directory in the .zip file
    and all the other files and directories are located withn that directory.

        file.zip
            |- main_dir
                |- _rime_settings.db
                |- sdcard
                    |- ...
                |- data
                    |- ...
    """
    path = Path(zf)
    for element in path.iterdir():
        if element.is_dir():
            return element

    raise ValueError("The zipfile does not contain a single directory.")

def path_to_info(zf: ZipFile, path: Path) -> ZipInfo:
    """
    Convert a Path to a PathInfo object.
    """
    return zf.getinfo(str(path))

class ZippedFilesystem:
    def __init__(self, zipped_pathname):
        self.zipped_pathname = zipped_pathname
        self.unzipped_dirname = self.zipped_pathname_to_unzipped_dirname(zipped_pathname)

        if os.path.exists(self.unzipped_dirname):
            if not self._is_unzipped():
                shutil.rmtree(self.unzipped_dirname)

        if not self._is_unzipped():
            self._unzip()

    def _is_unzipped(self):
        return os.path.exists(os.path.join(self.unzipped_dirname, 'complete'))

    def _unzip(self):
        os.makedirs(self.unzipped_dirname, exist_ok=True)

        with ZipFile(self.zipped_pathname) as zf:
            zf.extractall(self.unzipped_dirname)

        with open(os.path.join(self.unzipped_dirname, 'complete'), 'w') as f:
            f.write(str(time.time()))

    @classmethod
    def zipped_pathname_to_unzipped_dirname(cls, zipped_pathname):
        """
        Convert a zipped pathname to an unzipped directory name.
        """
        dirname = os.path.dirname(zipped_pathname)
        filename = os.path.splitext(os.path.basename(zipped_pathname))[0]

        return os.path.join(dirname, f'_unzipped_{filename}')

def temp_file_name() -> str:
    """
    Return a temporary file name. This is subject to race conditions but is the best we can do for Windows.
    """
    pathname = None

    for _ in range(10):
        pathname = os.path.join(tempfile.gettempdir(), 'tmp' + secrets.token_hex(8))
        if not os.path.exists(pathname):
            break
    else:
        pathname = None

    if not pathname:
        raise FileExistsError("Could not create a temporary file.")

    return pathname

class TmpFile:
    """
    Produce a Windows-friendly temporary file which can be used as a context manager.
    """
    def __init__(self):
        self.pathname = temp_file_name()

    def __del__(self):
        if os.path.exists(self.pathname):
            os.unlink(self.pathname)

    def open(self, mode='w+b'):
        return open(self.pathname, mode)

    @contextmanager
    def context_manager(self, fn, *args, **kw):
        try:
            yield fn(*args, **kw)
        finally:
            if os.path.exists(self.pathname):
                os.unlink(self.pathname)
