from ffmpegio import ffmpeg


# out = ffmpeg.parse("ffmpeg -i input.avi -b:v 64k -bufsize 64k output.avi")
# print(out)


s = r"ffmpeg -i input.ts -filter_complex \
  '[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay' \
  -sn -map '#0x2dc' -map a output.mkv"
# p = ffmpeg.parse(s)
# print(p["global_options"])
# print(p["inputs"])
# print(p["outputs"])


# s = r"-filter_complex \
#   '[#0x2ef] setpts=PTS+1/TB [sub] ; [#0x2d0] [sub] overlay' \
#   -sn -map '#0x2dc'"
# print(ffmpeg.parse(s, no_output_url=True))

# s = "ffmpeg -i /tmp/a.wav -map 0:a -b:a 64k /tmp/a.mp2 -map 0:a -b:a 128k /tmp/b.mp2"
p = ffmpeg.parse(s)
print(p)
print(ffmpeg.compose(**p))
print(ffmpeg.compose(**p,shell_command=True))

ffmpeg.find()
print(ffmpeg.FFMPEG_BIN)
print(ffmpeg.FFPROBE_BIN)
