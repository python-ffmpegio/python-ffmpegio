"""Search additional paths in Windows

The :py:func:`finder <ffmpegio.plugins.hookspecs.finder>` hook of this built-in plugin module returns the full paths
of :file:`ffmpeg` and :file:`ffprobe` if both executables are found in one of the following 
search paths:

    * :file:`%PROGRAMFILES%\\\\ffmpeg\\\\bin`
    * :file:`%PROGRAMFILES(X86)%\\\\ffmpeg\\\\bin`
    * :file:`%USERPROFILE%\\\\ffmpeg\\\\bin`
    * :file:`%APPDATA%\\\\ffmpeg\\\\bin`
    * :file:`%APPDATA%\\\\programs\\\\ffmpeg\\\\bin`
    * :file:`%LOCALAPPDATA%\\\\ffmpeg\\\\bin`
    * :file:`%LOCALAPPDATA%\\\\programs\\\\ffmpeg\\\\bin`

Here, :file:`%xxx%` are the standard Windows environmental variables:

    ===============================  =====================================
    Windows Environmental Variables  Example path
    ===============================  =====================================
    :code:`%PROGRAMFILES%`           :file:`C:\\\\Program Files`
    :code:`%PROGRAMFILES(X86)%`      :file:`C:\\\\Program Files (x86)`
    :code:`%USERPROFILE%`            :file:`C:\\\\Users\\\\john`
    :code:`%APPDATA%`                :file:`C:\\\\Users\\\\john\\\\AppData\\\\Roaming`
    :code:`%LOCALAPPDATA%`           :file:`C:\\\\Users\\\\john\\\\AppData\\\\Local`
    ===============================  =====================================
"""

from __future__ import annotations

import os
import shutil

from pluggy import HookimplMarker

hookimpl = HookimplMarker("ffmpegio")


@hookimpl
def finder():
    """Set path to FFmpeg bin directory

    The following paths are tested in the order appeared:

    * :code:`%PROGRAMFILES%\\ffmpeg\\bin`
    * :code:`%PROGRAMFILES(X86)%\\ffmpeg\\bin`
    * :code:`%USERPROFILE%\\ffmpeg\\bin`
    * :code:`%APPDATA%\\ffmpeg\\bin`
    * :code:`%APPDATA%\\programs\\ffmpeg\\bin`
    * :code:`%LOCALAPPDATA%\\ffmpeg\\bin`
    * :code:`%LOCALAPPDATA%\\programs\\ffmpeg\\bin`

    Here, :code:`%xxx%` are the standard Windows environmental variables:

    ===============================  =====================================
    Windows Environmental Variables  Example path
    ===============================  =====================================
    :code:`%PROGRAMFILES%`               :code:`C:\\Program Files`
    :code:`%PROGRAMFILES(X86)%`          :code:`C:\\Program Files (x86)`
    :code:`%USERPROFILE%`                :code:`C:\\Users\\john`
    :code:`%APPDATA%`                    :code:`C:\\Users\\john\\AppData\\Roaming`
    :code:`%LOCALAPPDATA%`               :code:`C:\\Users\\john\\AppData\\Local`
    ===============================  =====================================

    When :code:`ffmpegio` is first imported in Python, it automatically run
    this function once, searching in the system path and Windows default
    locations (see above). If both ffmpeg and ffprobe are not found, a
    warning message is displayed.

    """

    try:
        dirs = [
            os.path.join(d, "ffmpeg", "bin")
            for d in (
                *(
                    os.environ[var]
                    for var in (
                        "PROGRAMFILES",
                        "PROGRAMFILES(X86)",
                        "USERPROFILE",
                        "APPDATA",
                        "LOCALAPPDATA",
                    )
                    if var in os.environ
                ),
                *(
                    os.path.join(os.environ[var], "Programs")
                    for var in (
                        "APPDATA",
                        "LOCALAPPDATA",
                    )
                    if var in os.environ
                ),
            )
        ]

        def search(cmd):
            for d in dirs:
                p = shutil.which(os.path.join(d, cmd))
                if p:
                    return p
            return None

        ffmpeg_path = search("ffmpeg.exe")
        ffprobe_path = search("ffprobe.exe")

        return (ffmpeg_path or ffprobe_path) and (ffmpeg_path, ffprobe_path)

    except:
        return None
