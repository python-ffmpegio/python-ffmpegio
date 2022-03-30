from ffmpegio import devices
import logging


def test_devices():
    devices.scan()
    print(devices.SOURCES)
    print(devices.SINKS)

    for dev in devices.list_video_sources():
        print(dev, devices.resolve_source("v:0", {"f": dev}))
        print(dev, devices.list_hardware(dev,'source'))
        print(devices.list_source_options(dev, 'v:0'))
    for dev in devices.list_audio_sources():
        print(dev, devices.resolve_source("a:0", {"f": dev}))
        print(dev, devices.list_hardware(dev,'source'))
        print(devices.list_source_options(dev,'a:0'))

    for dev in devices.list_video_sinks():
        print(dev, devices.resolve_sink("v:0", {"f": dev}))
        print(dev, devices.list_hardware(dev,'sink'))
        print(devices.list_sink_options(dev,'v:0'))
    for dev in devices.list_audio_sinks():
        print(dev, devices.resolve_sink("v:0", {"f": dev}))
        print(dev, devices.list_hardware(dev,'sink'))
        print(devices.list_sink_options(dev,'a:0'))


if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)

    # if ffmpegio.path.FFMPEG_VER != "5.0":
    #     v5 = r"C:\Users\tikuma\AppData\Local\Programs\ffmpeg-5.0\bin"
    #     ffmpegio.set_path(fr"{v5}\ffmpeg.exe", fr"{v5}\ffprobe.exe")
    #     print(ffmpegio.path.FFMPEG_VER)

    test_devices()
