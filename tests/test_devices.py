from ffmpegio import devices
import logging


def test_devices():
    devices.scan()
    print(devices.SOURCES)
    print(devices.SINKS)

    print(devices.list_sources("dshow", "video"))
    print(devices.list_sources(return_nested=True))

    try:
        (dev, hw_enum), name = next((i for i in devices.list_sources().items()), None)
        print(f"({dev},{hw_enum}): {name}")
        print(devices.get_source_info(dev, hw_enum))
        print(dev, devices.resolve_source(hw_enum, {"f": dev}))
        print(dev, devices.resolve_source(f"{dev}:{hw_enum}", None))
        print(devices.list_source_options(dev, hw_enum))

        print(devices.resolve_source(f"dshow:v:0|a:0", None))

    except:
        print("no source device found")

    print(devices.list_sinks("dshow", "video"))
    print(devices.list_sinks("dshow", "audio", return_nested=True))
    try:
        (dev, hw_enum), name = next((i for i in devices.list_sources().items()), None)
        print(f"({dev},{hw_enum}): {name}")
        print(devices.get_sink_info(dev, hw_enum))
        print(dev, devices.resolve_sink(hw_enum, {"f": dev}))
        print(devices.list_sink_options(dev, hw_enum))
    except:
        print("no sink device found")


if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)

    # if ffmpegio.path.FFMPEG_VER != "5.0":
    #     v5 = r"C:\Users\tikuma\AppData\Local\Programs\ffmpeg-5.0\bin"
    #     ffmpegio.set_path(fr"{v5}\ffmpeg.exe", fr"{v5}\ffprobe.exe")
    #     print(ffmpegio.path.FFMPEG_VER)

    test_devices()
