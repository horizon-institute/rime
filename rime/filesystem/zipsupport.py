import os
import secrets
import tempfile
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
