`ffmpegio-core`: Media I/O with FFmpeg in Python
===================================================

|pypi| |pypi-status| |pypi-pyvers| |github-license| |github-status|

.. |pypi| image:: https://img.shields.io/pypi/v/ffmpegio
  :alt: PyPI
.. |pypi-status| image:: https://img.shields.io/pypi/status/ffmpegio
  :alt: PyPI - Status
.. |pypi-pyvers| image:: https://img.shields.io/pypi/pyversions/ffmpegio
  :alt: PyPI - Python Version
.. |github-license| image:: https://img.shields.io/github/license/python-ffmpegio/python-ffmpegio
  :alt: GitHub License
.. |github-status| image:: https://img.shields.io/github/workflow/status/python-ffmpegio/python-ffmpegio/Run%20Tests
  :alt: GitHub Workflow Status

Python `ffmpegio` package aims to bring the full capability of `FFmpeg <https://ffmpeg.org>`__
to read, write, probe, and manipulate multimedia data to Python. FFmpeg is an open-source cross-platform 
multimedia framework, which can handle most of the multimedia formats available today.

.. note::
  
  Since v0.3.0, `ffmpegio` Python distribution package has been split into `ffmpegio-core` and `ffmpegio` to allow
  Numpy-independent installation.

Install the full `ffmpegio` package via ``pip``:

.. code-block:: bash

   pip install ffmpegio

If `numpy.ndarray` data I/O is not needed, instead use 

.. code-block:: bash

   pip install ffmpegio-core

Main Features
-------------

* Pure-Python light-weight package interacting with FFmpeg executable found in 
  the system
* Transcode a media file to another in Python
* Read, write, filter, and create functions for audio, image, and video data
* Context-managing `ffmpegio.open` to perform stream read/write operations of video and audio
* Automatically detect and convert audio & video formats to and from `numpy.ndarray` properties
* Probe media file information
* Accepts all FFmpeg options including filter graphs
* Supports a user callback whenever FFmpeg updates its progress information file 
  (see `-progress` FFmpeg option)
* `ffconcat` scripter to make the use of `-f concat` demuxer easier
* I/O device enumeration to eliminate the need to look up device names. (currently supports only: Windows DirectShow)
* More features to follow

Documentation
-------------

Visit our `GitHub page here <https://python-ffmpegio.github.io/python-ffmpegio/>`__

Examples
--------

To import `ffmpegio`

.. code-block:: python

  >>> import ffmpegio

- `Transcoding <transcoding_>`_
- `Read Audio Files <Read Audio Files_>`_
- `Read Image Files / Capture Video Frames <Read Image Files / Capture Video Frames_>`_
- `Read Video Files <Read Video Files_>`_
- `Read Multiple Files or Streams <Read Multiple Files or Streams_>`_
- `Write Audio, Image, & Video Files <Write Audio, Image, & Video Files_>`_
- `Filter Audio, Image, & Video Data <Filter Audio, Image, & Video Data_>`_
- `Stream I/O <Stream I/O_>`_
- `Device I/O Enumeration <Device I/O Enumeration_>`_
- `Progress Callback <Progress Callback_>`_
- `Filtergraph Builder`_
- `Run FFmpeg and FFprobe Directly <Run FFmpeg and FFprobe Directly_>`_

Transcoding
^^^^^^^^^^^

.. code-block:: python

  >>> # transcode, overwrite output file if exists, showing the FFmpeg log
  >>> ffmpegio.transcode('input.avi', 'output.mp4', overwrite=True, show_log=True) 

  >>> # 1-pass H.264 transcoding
  >>> ffmpegio.transcode('input.avi', 'output.mkv', vcodec='libx264', show_log=True,
  >>>                    preset='slow', crf=22, acodec='copy') 

  >>> # 2-pass H.264 transcoding
  >>> ffmpegio.transcode('input.avi', 'output.mkv', two_pass=True, show_log=True,
  >>>                    **{'c:v':'libx264', 'b:v':'2600k', 'c:a':'aac', 'b:a':'128k'}) 

  >>> # concatenate videos using concat demuxer
  >>> files = ['/video/video1.mkv','/video/video2.mkv']
  >>> ffconcat = ffmpegio.FFConcat()
  >>> ffconcat.add_files(files)
  >>> with ffconcat: # generates temporary ffconcat file
  >>>     ffmpegio.transcode(ffconcat, 'output.mkv', f_in='concat', codec='copy', safe_in=0)

Read Audio Files
^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> # read audio samples in its native sample format and return all channels
  >>> fs, x = ffmpegio.audio.read('myaudio.wav') 
  >>> # fs: sampling rate in samples/second, x: [nsamples x nchannels] numpy array

  >>> # read audio samples from 24.15 seconds to 63.2 seconds, pre-convert to mono in float data type 
  >>> fs, x = ffmpegio.audio.read('myaudio.flac', ss=24.15, to=63.2, sample_fmt='dbl', ac=1)

  >>> # read filtered audio samples first 10 seconds
  >>> #   filter: equalizer which attenuate 10 dB at 1 kHz with a bandwidth of 200 Hz 
  >>> fs, x = ffmpegio.audio.read('myaudio.mp3', t=10.0, af='equalizer=f=1000:t=h:width=200:g=-10')

Read Image Files / Capture Video Frames
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> # list supported image extensions
  >>> ffmpegio.caps.muxer_info('image2')['extensions']
  ['bmp', 'dpx', 'exr', 'jls', 'jpeg', 'jpg', 'ljpg', 'pam', 'pbm', 'pcx', 'pfm', 'pgm', 'pgmyuv', 
   'png', 'ppm', 'sgi', 'tga', 'tif', 'tiff', 'jp2', 'j2c', 'j2k', 'xwd', 'sun', 'ras', 'rs', 'im1', 
   'im8', 'im24', 'sunras', 'xbm', 'xface', 'pix', 'y']

  >>> # read BMP image with auto-detected pixel format (rgb24, gray, rgba, or ya8)
  >>> I = ffmpegio.image.read('myimage.bmp') # I: [height x width x ncomp] numpy array

  >>> # read JPEG image, then convert to grayscale and proportionally scale so the width is 480 pixels
  >>> I = ffmpegio.image.read('myimage.jpg', pix_fmt='grayscale', s='480x-1')

  >>> # read PNG image with transparency, convert it to plain RGB by filling transparent pixels orange
  >>> I = ffmpegio.image.read('myimage.png', pix_fmt='rgb24', fill_color='orange')

  >>> # capture video frame at timestamp=4:25.3 and convert non-square pixels to square
  >>> I = ffmpegio.image.read('myvideo.mpg', ss='4:25.3', square_pixels='upscale')

  >>> # capture 5 video frames and tile them on 3x2 grid with 7px between them, and 2px of initial margin
  >>> I = ffmpegio.image.read('myvideo.mp4', vf='tile=3x2:nb_frames=5:padding=7:margin=2')

  >>> # create spectrogram of the audio input (must specify pix_fmt if input is audio)
  >>> I = ffmpegio.image.read('myaudio.mp3', filter_complex='showspectrumpic=s=960x540', pix_fmt='rgb24')


Read Video Files
^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> # read 50 video frames at t=00:32:40 then convert to grayscale
  >>> fs, F = ffmpegio.video.read('myvideo.mp4', ss='00:32:40', vframes=50, pix_fmt='gray')
  >>> #  fs: frame rate in frames/second, F: [nframes x height x width x ncomp] numpy array

  >>> # get running spectrogram of audio input (must specify pix_fmt if input is audio)
  >>> fs, F = ffmpegio.video.read('myvideo.mp4', pix_fmt='rgb24', filter_complex='showspectrum=s=1280x480')
  

Read Multiple Files or Streams
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> # read both video and audio streams (1 ea)
  >>> rates, data = ffmpegio.media.read('mymedia.mp4')
  >>> #  rates: dict of frame rate and sampling rate: keys="v:0" and "a:0"
  >>> #  data: dict of video frame array and audio sample array: keys="v:0" and "a:0"

  >>> # combine video and audio files
  >>> rates, data = ffmpegio.media.read('myvideo.mp4','myaudio.mp3')

  >>> # get output of complex filtergraph (can take multiple inputs)
  >>> expr = "[v:0]split=2[out0][l1];[l1]edgedetect[out1]"
  >>> rates, data = ffmpegio.media.read('myvideo.mp4',filter_complex=expr,map=['[out0]','[out1]'])
  >>> #  rates: dict of frame rates: keys="v:0" and "v:1"
  >>> #  data: dict of video frame arrays: keys="v:0" and "v:1"

Write Audio, Image, & Video Files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> # create a video file from a numpy array
  >>> ffmpegio.video.write('myvideo.mp4', rate, F)

  >>> # create an image file from a numpy array
  >>> ffmpegio.image.write('myimage.png', F)

  >>> # create an audio file from a numpy array
  >>> ffmpegio.audio.write('myaudio.mp3', rate, x)

Filter Audio, Image, & Video Data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> # Add fade-in and fade-out effects to audio data
  >>> fs_out, y = ffmpegio.audio.filter('afade=t=in:ss=0:d=15,afade=t=out:st=875:d=25', fs_in, x)

  >>> # Apply mirror effect to an image
  >>> I_out = ffmpegio.image.filter('crop=iw/2:ih:0:0,split[left][tmp];[tmp]hflip[right];[left][right] hstack', I_in)

  >>> # Add text at the center of the video frame
  >>> filter = "drawtext=fontsize=30:fontfile=FreeSerif.ttf:text='hello world':x=(w-text_w)/2:y=(h-text_h)/2"
  >>> fs_out, F_out = ffmpegio.video.filter(filter, fs_in, F_in)

Stream I/O
^^^^^^^^^^

.. code-block:: python

  >>> # process video 100 frames at a time and save output as a new video 
  >>> # with the same frame rate
  >>> with ffmpegio.open('myvideo.mp4', 'rv', blocksize=100) as fin,
  >>>      ffmpegio.open('myoutput.mp4', 'wv', rate=fin.rate) as fout:
  >>>     for frames in fin:
  >>>         fout.write(myprocess(frames))

Filtergraph Builder
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   >>> # build complex filtergraph
   >>> from ffmpegio import filtergraph as fgb
   >>>
   >>> v0 = "[0]" >> fgb.trim(start_frame=10, end_frame=20)
   >>> v1 = "[0]" >> fgb.trim(start_frame=30, end_frame=40)
   >>> v3 = "[1]" >> fgb.hflip()
   >>> v2 = (v0 | v1) + fgb.concat(2)
   >>> v5 = (v2|v3) + fgb.overlay(eof_action='repeat') + fgb.drawbox(50, 50, 120, 120, 'red', t=5)
   >>> v5
   <ffmpegio.filtergraph.Graph object at 0x1e67f955b80>
       FFmpeg expression: "[0]trim=start_frame=10:end_frame=20[L0];[0]trim=start_frame=30:end_frame=40[L1];[L0][L1]concat=2[L2];[1]hflip[L3];[L2][L3]overlay=eof_action=repeat,drawbox=50:50:120:120:red:t=5"
       Number of chains: 5
         chain[0]: [0]trim=start_frame=10:end_frame=20[L0];
         chain[1]: [0]trim=start_frame=30:end_frame=40[L1];
         chain[2]: [L0][L1]concat=2[L2];
         chain[3]: [1]hflip[L3];
         chain[4]: [L2][L3]overlay=eof_action=repeat,drawbox=50:50:120:120:red:t=5      
       Available input pads (0): 
       Available output pads: (1): (4, 1, 0)

Device I/O Enumeration
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> # record 5 minutes of audio from Windows microphone
  >>> fs, x = ffmpegio.audio.read('a:0', f_in='dshow', sample_fmt='dbl', t=300)

  >>> # capture Windows' webcam frame
  >>> with ffmpegio.open('v:0', 'rv', f_in='dshow') as webcam,
  >>>     for frame in webcam:
  >>>         process_frame(frame)

Progress Callback
^^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> import pprint

  >>> # progress callback
  >>> def progress(info, done):
  >>>     pprint(info) # bunch of stats
  >>>     if done:
  >>>        print('video decoding completed')
  >>>     else:
  >>>        return check_cancel_command(): # return True to kill immediately
  
  >>> # can be used in any butch processing
  >>> rate, F = ffmpegio.video.read('myvideo.mp4', progress=progress)

  >>> # as well as for stream processing
  >>> with ffmpegio.open('myvideo.mp4', 'rv', blocksize=100, progress=progress) as fin:
  >>>     for frames in fin:
  >>>         myprocess(frames)

Run FFmpeg and FFprobe Directly
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

  >>> from ffmpegio import ffmpeg, FFprobe, ffmpegprocess
  >>> from subprocess import PIPE

  >>> # call with options as a long string
  >>> ffmpeg('-i input.avi -b:v 64k -bufsize 64k output.avi')

  >>> # or call with list of options
  >>> ffmpeg(['-i', 'input.avi' ,'-r', '24', 'output.avi'])

  >>> # the same for ffprobe
  >>> ffprobe('ffprobe -show_streams -select_streams a INPUT')

  >>> # specify subprocess arguments to capture stdout
  >>> out = ffprobe('ffprobe -of json -show_frames INPUT', 
                    stdout=PIPE, universal_newlines=True).stdout

  >>> # use ffmpegprocess to take advantage of ffmpegio's default behaviors
  >>> out = ffmpegprocess.run({"inputs": [("input.avi", None)],
                               "outputs": [("out1.mp4", None),
                                           ("-", {"f": "rawvideo", "vframes": 1, "pix_fmt": "gray", "an": None})
                              }, capture_log=True)
  >>> print(out.stderr) # print the captured FFmpeg logs (banner text omitted)
   >>> b = out.stdout # width*height bytes of the first frame
