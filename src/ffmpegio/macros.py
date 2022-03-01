'''ffmpegio.macro - Macro plugin handler

Users can create plugin macro modules to load their often-use FFmpeg commands automatically whenever
ffmpegio package is imported.

The plugin module shall create `macro` hook(s):



'''

from . import plugins

def __getattr__(name):  # per PEP 562
    plugins
    try:
        return {
            "ffmpeg_dir": _ffmpeg_dir,
            "ffmpeg_path": lambda: _ffmpeg_version()
            and path.join(_ffmpeg_dir(), "ffmpeg" if os_name != "nt" else "ffmpeg.exe"),
            "ffprobe_path": lambda: _ffmpeg_version()
            and path.join(
                _ffmpeg_dir(), "ffprobe" if os_name != "nt" else "ffprobe.exe"
            ),
            "ffmpeg_version": _ffmpeg_version,
        }[name]()
    except:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    return []