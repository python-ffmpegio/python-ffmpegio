from ffmpegio import ffmpeg, probe

# url = "tests/assets/testaudio-1m.mp3"
url = "tests/assets/testmulti-1m.mp4"

print(probe.full_details(url,select_streams=[2]))
