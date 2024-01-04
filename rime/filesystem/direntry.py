from dataclasses import dataclass
import mimetypes
import os
import stat

from filetype import guess as filetype_guess

# MIME type for DirEntries which haven't yet had their MIME type determined
MIME_TYPE_NOT_YET_DETERMINED = 'rime/mime-type-not-yet-determined'

# MIME type for DirEntries which we tried but failed to determine a MIME type for
# (e.g. because the file is empty)
MIME_TYPE_CANNOT_DETERMINE = 'rime/mime-type-cannot-determine'

MIME_TYPE_DIRECTORY = 'inode/directory'

# Chosen by fair dice roll.
# Just kidding, chosen by reference to https://github.com/h2non/filetype.py
FILE_HEADER_GUESS_LENGTH = 261

@dataclass(eq=True, frozen=True)
class DirEntry:
    """
    Represents a file or directory on a device.
    """
    path: str  # Full path name
    stat_val: os.stat_result
    mime_type: str

    def is_dir(self):
        return stat.S_ISDIR(self.stat_val.st_mode)

    def is_file(self):
        return stat.S_ISREG(self.stat_val.st_mode)

    def stat(self):
        return self.stat_val

    @classmethod
    def from_path(cls, fs, path):
        stat_val = fs.stat(path)

        if stat.S_ISDIR(stat_val.st_mode):
            mime_type = MIME_TYPE_DIRECTORY
        elif stat.S_ISREG(stat_val.st_mode):
            with fs.open(path) as f:
                first_bytes = f.read(FILE_HEADER_GUESS_LENGTH)

            if not first_bytes:
                mime_type = MIME_TYPE_CANNOT_DETERMINE
            else:
                filetype = filetype_guess(first_bytes)
                if filetype is None:
                    mime_type = mimetypes.guess_type(path)[0] or MIME_TYPE_CANNOT_DETERMINE
                else:
                    mime_type = filetype.mime
        else:
            mime_type = MIME_TYPE_CANNOT_DETERMINE
        
        return cls(path, stat_val, mime_type)
