import time
from ffmpegio import ffmpeg, utils, audio
import subprocess as sp
from ffmpegio.utils import threaded_pipe as tp

# logging.basicConfig(level=logging.DEBUG)


url = "tests/assets/testaudio-1m.mp3"
sample_fmt = "s16"
out_codec, dtype = utils.get_audio_format(sample_fmt)
container = out_codec[4:]

fs, s = audio.read(url, sample_fmt=sample_fmt)

args = {
    "inputs": [("-", {"f": "mp3"})],
    "outputs": [("-", {"f": container, "c:a": out_codec, "sample_fmt": sample_fmt})],
}

with open(url, "rb") as f:
    bytes = f.read()  # byte array


feed = tp.ThreadedPipe(True)
read = tp.ThreadedPipe(False)

feed.start()
read.start()

feed.open()
read.open()

proc = ffmpeg._run(sp.Popen, args, stdin=feed.fileno(), stdout=read.fileno())

try:
    feed.queue.put(bytes)

    time.sleep(0.1)
    print(f'# of data blocks: {read.queue.qsize()}')

    time.sleep(0.1)
    print(f'# of data blocks: {read.queue.qsize()}')

    for i in range(100):
        data = read.queue.get(True, 1)
        try:
            print(f"{i}: {len(data)} bytes")
        except tp.Empty:
            print(f"{i}: empty")
except:
    proc.kill()
finally:
    feed.join()
    read.join()
    proc.wait()
