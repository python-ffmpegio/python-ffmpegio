from ffmpegio import devices
import logging


def test_devices():
    devices.rescan()
    print(devices.SOURCES)
    print(devices.SINKS)

    print(devices.list_hardware("dshow"))
    print(devices.list_hardware("dshow", "source"))

    for dev in devices.list_video_sources():
        print(dev, devices.resolve_source("v:0", {"f": dev}))
        print(dev, devices.list_hardware(dev,'source'))
    for dev in devices.list_audio_sources():
        print(dev, devices.resolve_source("a:0", {"f": dev}))
        print(dev, devices.list_hardware(dev,'source'))

    for dev in devices.list_video_sinks():
        print(dev, devices.resolve_sink("v:0", {"f": dev}))
        print(dev, devices.list_hardware(dev,'sink'))
    for dev in devices.list_audio_sinks():
        print(dev, devices.resolve_sink("v:0", {"f": dev}))
        print(dev, devices.list_hardware(dev,'sink'))


if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)

    # if ffmpegio.path.FFMPEG_VER != "5.0":
    #     v5 = r"C:\Users\tikuma\AppData\Local\Programs\ffmpeg-5.0\bin"
    #     ffmpegio.set_path(fr"{v5}\ffmpeg.exe", fr"{v5}\ffprobe.exe")
    #     print(ffmpegio.path.FFMPEG_VER)

    test_devices()
