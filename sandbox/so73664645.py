# 73664645

from subprocess import DEVNULL, PIPE
import ffmpegio

# nch = 16
for i, nch in enumerate([3, 6]):
    cmd = f'-f lavfi -i aevalsrc=\'{"|".join(["-2+random(0)"]*nch)}:d=1\' -y sandbox/in{i}.wav'
    ffmpegio.ffmpeg(cmd)

cmd = "-y -i sandbox/in0.wav -i sandbox/in1.wav -filter_complex 'aevalsrc='0|0|0|0|0|0|0'[anull];[0:a][1:a][anull]amerge=inputs=3[aout]' -map [aout] -shortest -c:a aac 'sandbox/out.m4a'"
ffmpegio.ffmpeg(cmd)

for nch in range(1, 25):
    cmd = f'-f lavfi -i aevalsrc=\'{"|".join(["-2+random(0)"]*nch)}:d=1\' -y -c:a aac sandbox/output.m4a'
    if not ffmpegio.ffmpeg(cmd, stderr=PIPE).returncode:
        # print(f"failed to encode {nch} channels")
    # else:
        print(f"successfully encoded {nch} channels")

# https://trac.ffmpeg.org/wiki/Encode/AAC
