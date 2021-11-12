import time
from ffmpegio import ffmpeg, utils, audio
import subprocess as sp
from ffmpegio import io

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


feed = io.QueuedWriter()
read = io.QueuedReader()

proc = ffmpeg._run(sp.Popen, args, stdin=feed.fileno(), stdout=read.fileno())

try:
    feed.write(bytes)
    feed.mark_eof()

    # time.sleep(0.1)
    # print(f'# of data blocks: {read._pipe.queue.qsize()}')

    # time.sleep(0.1)
    # print(f'# of data blocks: {read._pipe.queue.qsize()}')

    # proc.wait()
    # print(f'# of data blocks: {read._pipe.queue.qsize()}')

    for i in range(100):
        data = read.read(8192, timeout=1)
        if data is None:
            break
        try:
            print(f"{i}: {len(data)} bytes")
        except io.TimeoutExpired:
            print(f"{i}: empty")
except Exception as e:
    proc.kill()
    print(e)
finally:
    feed._pipe.join()
    read._pipe.join()
    proc.wait()
