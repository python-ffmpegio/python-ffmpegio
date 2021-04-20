from ffmpegio import configure, probe, caps, filter, utils, ffmpeg

# url = 'tests/assets/testvideo-5m.mpg'
url = "tests/assets/ffmpeg-logo.png"
# url = 'tests/assets/testvideo-43.avi'
# url = 'tests/assets/testaudio-one.wav'

def test_image_stream():
    info = probe.video_streams_basic(url)
    config = configure.image_stream(
        0,
        info[0],
        {
            "pix_fmt": "rgb24",
            "fill_color": "black",
            "flip": "both",
            "rotate": 360 / 24,
            "crop": (5, 8, 10, 12),
            "transpose": 1,
            "deinterlace": "yadif",
            "scale": (1 / 3, 1 / 2),
            "size": (1000, 120),
        },
    )
    print(config)
    pix_fmt, filt_def, bg_src, shape, dtype = config

    if filt_def:
        input_labels = (
            {utils.spec_stream(1, "v"): (0, 0), utils.spec_stream(0, "v"): (0, 1)}
            if bg_src
            else {}
        )
        print(filt_def)
        print(filter.compose_graph((filt_def,), input_labels=input_labels))

def test_finalize_opts():
    print(configure.finalize_opts({"video_flip":"both"}, configure._image_opts, default={"flip":"vertical"}, prefix="video_"))

def test_image_file():
    print(configure.image_file(url))

config = configure.video_io(url,video_pix_fmt="rgb24",prefix="video_",video_size=(1080,720))
print(config)
