from zipfile import ZipFile, Path

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
