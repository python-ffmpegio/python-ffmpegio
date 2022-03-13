from ffmpegio import devices
import ffmpegio
import logging

if __name__ == "__main__":
    from ffmpegio.ffmpegprocess import _exec, PIPE, DEVNULL
    from ffmpegio import plugins
    import re

    logging.basicConfig(level=logging.DEBUG)

    # if ffmpegio.path.FFMPEG_VER != "5.0":
    #     v5 = r"C:\Users\tikuma\AppData\Local\Programs\ffmpeg-5.0\bin"
    #     ffmpegio.set_path(fr"{v5}\ffmpeg.exe", fr"{v5}\ffprobe.exe")
    #     print(ffmpegio.path.FFMPEG_VER)

    devices.rescan()
    print(devices.SOURCES)
    print(devices.SINKS)
