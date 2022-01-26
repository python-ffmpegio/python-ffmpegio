import ffmpegio

print("CREATE Movie")
print(f"ffmpeg ver: {ffmpegio.ffmpeg_info()}")


# fileName = self.generateFilename()
fileName = 'sandbox/test_filtered_videoout.mp4'
fpsin, frames = ffmpegio.video.read('tests/assets/testvideo-1m.mp4',vframes=10)
nFrames = frames.shape[0]
fps = 16
with ffmpegio.open(fileName,'wv', rate=fps, vf='vflip,hflip,transpose', show_log=True, overwrite=True) as out:
    for frame in range(nFrames):
        myImg = frames[frame]
        # global_norm = np.true_divide((myImg - minV), (maxV - minV))
        # norm = (global_norm * 255)
        # intNorm = norm.astype(int)

        out.write(myImg)
