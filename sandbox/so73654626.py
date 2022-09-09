import ffmpegio
import subprocess as sp

ffmpegio.ffmpeg("-y -f lavfi -i testsrc=size=640x480:rate=1:duration=10 sandbox/in.mp4")

p2 = ffmpegio.ffmpeg(
    '-y -i sandbox/in.mp4 -f nut -i pipe: -filter_complex "[0:v][1:v]libvmaf=log_path=sandbox/log.json" -map 1 -c:v:1 copy sandbox/out.mp4',
    sp_run=sp.Popen,
    stdin=sp.PIPE,
)
p1 = ffmpegio.ffmpeg(
    '-i sandbox/in.mp4 -vcodec libx264 -crf 27 -f nut pipe:"',
    sp_run=sp.Popen,
    stdout=p2.stdin,
)
p1.wait()
try:
    p2.wait(1)
except:
    p2.kill()
