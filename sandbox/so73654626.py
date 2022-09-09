import ffmpegio
import subprocess as sp

ffmpegio.ffmpeg(
    "-y -f lavfi -i testsrc=size=640x480:rate=1:duration=100 sandbox/in.mp4"
)

cmd1 = "-loglevel quiet -i sandbox/in.mp4 -vcodec libx264 -crf 27 -f nut pipe:"
cmd2 = '-loglevel debug -y -i sandbox/in.mp4 -f nut -i pipe: -filter_complex "[0:v][1:v]libvmaf=log_fmt=json:log_path=sandbox/log.json,nullsink" -map 1 -c:v:1 copy sandbox/out.mp4'

ffmpeg = ffmpegio.get_path()
fullcmd = f"{ffmpeg} {cmd1}|{ffmpeg} {cmd2}"
sp.run(fullcmd, shell=True)

print(f"ffmpeg {cmd1}|ffmpeg {cmd2}")
