import os, shutil
from pluggy import HookimplMarker

hookimpl = HookimplMarker("ffmpegio")

@hookimpl
def finder():
    """Set path to FFmpeg bin directory

    :param dir: full path of the FFmpeg bin directory, defaults to None, which
                only look in the default locations
    :type dir: str, optional
    :raises Exception: if failed to find ffmpeg or ffprobe binary

    In Linux and Mac, only the specified directory or the system path are
    checked. In Windows, the following additional paths are tested in this order:

    * ``%PROGRAMFILES%\\ffmpeg\\bin``
    * ``%PROGRAMFILES(X86)%\\ffmpeg\\bin``
    * ``%USERPROFILE%\\ffmpeg\\bin``
    * ``%APPDATA%\\ffmpeg\\bin``
    * ``%APPDATA%\\programs\\ffmpeg\\bin``
    * ``%LOCALAPPDATA%\\ffmpeg\\bin``
    * ``%LOCALAPPDATA%\\programs\\ffmpeg\\bin``

    Here, ``%xxx%`` are the standard Windows environmental variables:

    ===============================  =====================================
    Windows Environmental Variables  Example path
    ===============================  =====================================
    ``%PROGRAMFILES%``               ``C:\\Program Files``
    ``%PROGRAMFILES(X86)%``          ``C:\\Program Files (x86)``
    ``%USERPROFILE%``                ``C:\\Users\\john``
    ``%APPDATA%``                    ``C:\\Users\\john\\AppData\\Roaming``
    ``%LOCALAPPDATA%``               ``C:\\Users\\john\\AppData\\Local``
    ===============================  =====================================

    When :py:mod:`ffmpegio` is first imported in Python, it automatically run
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