from ffmpegio import audio, probe
import tempfile, re, logging
from os import path

logging.basicConfig(level=logging.DEBUG)

def test_read():

    url = "tests/assets/testvideo-5m.mpg"

    T = 0.51111
    fs, x = audio.read(url, duration=T)
    print(int(fs * T), x.shape)
    assert int(fs * T) == x.shape[0]

    T = 1.5
    t0 = 0.5
    fs, x1 = audio.read(url, start=t0, end=t0+T)
    print(int(fs * T), x1.shape)
    assert int(fs * T) == x1.shape[0]


def test_read_write():
    # url = "tests/assets/testaudio-one.wav"
    # url = "tests/assets/testaudio-two.wav"
    # url = "tests/assets/testaudio-three.wav"
    url = "tests/assets/testvideo-5m.mpg"
    # url = "tests/assets/testvideo-43.avi"
    # url = "tests/assets/testvideo-169.avi"
    # url = r"C:\Users\tikum\Music\(アルバム) [Jazz Fusion] T-SQUARE - T-Square Live featuring F-1 Grand Prix Theme [EAC] (flac+cue).mka"
    outext = ".flac"

    # fmts = caps.samplefmts()
    # print(fmts)

    info = probe.audio_streams_basic(
        url, index=0, entries=("sample_rate", "sample_fmt", "channels")
    )[0]

    print(info)

    fs, x = audio.read(url)

    with tempfile.TemporaryDirectory() as tmpdirname:

        print(probe.audio_streams_basic(url))
        out_url = path.join(tmpdirname, re.sub(r"\..*?$", outext, path.basename(url)))
        print(out_url)
        print(x.shape, x.dtype)
        audio.write(out_url, fs, x)
        fs, y = audio.read(out_url, sample_fmt="flt")
        print(probe.audio_streams_basic(out_url))

    #     with open(path.join(tmpdirname, "progress.txt")) as f:
    #         print(f.read())

    # display = os.read(read_pipe, 128).strip()

    # t = np.arange(x.shape[0])/fs
    # plt.plot(t,x,t,y)
    # plt.show()


# test_read()