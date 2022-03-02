from pypylon import pylon
import ffmpegio

camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
camera.Open()

with ffmpegio.open(
    "output.mp4",
    "wv",
    rate_in=45,
    vsync_in=0,
    extra_hw_frames_in=2,
    overwrite=True,
    vcodec="h264_nvenc",
) as mp4:
    while camera.IsGrabbing():
        grabResult = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        if grabResult.GrabSucceeded():
            img = (
                grabResult.GetArray()
            )  # or GetArrayZeroCopy() ? Make sure img shape is [nframes x h x w x ncomp]
            mp4.write(img)

        grabResult.Release()
camera.Close()

# ffmpeg -y -f rawvideo -pix_fmt rgb24 -vsync 0 -extra_hw_frames 2 -s 2000x2000 -r 45 -i - -an -c:v h264_nvenc output.mp4
