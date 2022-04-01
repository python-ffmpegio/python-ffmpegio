from ffmpegio import devices, audio, open, transcode, video
from tempfile import TemporaryDirectory
from os import path
import logging

# logging.basicConfig(level=logging.DEBUG)


def test_devices():
    devices.scan()
    print(devices.SOURCES)
    print(devices.SINKS)

    print(devices.list_sources("dshow", "video"))
    print(devices.list_sources(return_nested=True))

    try:
        (dev, hw_enum), name = next((i for i in devices.list_sources().items()))
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
        (dev, hw_enum), name = next((i for i in devices.list_sources().items()))
        print(f"({dev},{hw_enum}): {name}")
        print(devices.get_sink_info(dev, hw_enum))
        print(dev, devices.resolve_sink(hw_enum, {"f": dev}))
        print(devices.list_sink_options(dev, hw_enum))
    except:
        print("no sink device found")


def try_devices():
    devices.scan()

    print(devices.list_sources())

    print(devices.list_source_options("dshow", "v:0"))
    print(devices.list_source_options("dshow", "a:0"))

    fs, x = video.read("v:0", f_in="dshow", t=1, show_log=True)

    # capture 10 seconds of audio
    fs, x = audio.read("a:0", f_in="dshow", t=1, show_log=True)
    print(f"[a:0] rate={fs}, data={[*x.keys()]}")

    # stream webcam video feed for
    with open("v:0", "rv", f_in="dshow", show_log=True) as dev:
        print(f"[v:0] rate={dev.rate}")
        for i, frame in enumerate(dev):
            print(f"Frame {i}: {[*frame.keys()]}")
            break

    # save video and audio to mp4 file
    # - if a device support multiple streams, specify their enums separated by '|'
    with TemporaryDirectory() as tempdir:
        transcode(
            "v:0|a:0",
            path.join(tempdir, "captured.mp4"),
            f_in="dshow",
            t_in=1,
            show_log=True,
        )


if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)

    # if ffmpegio.path.FFMPEG_VER != "5.0":
    #     v5 = r"C:\Users\tikuma\AppData\Local\Programs\ffmpeg-5.0\bin"
    #     ffmpegio.set_path(fr"{v5}\ffmpeg.exe", fr"{v5}\ffprobe.exe")
    #     print(ffmpegio.path.FFMPEG_VER)

    # test_devices()
    try_devices()
