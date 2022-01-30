
class AviMediaReader:
    """Read video frames

    :param *urls: URLs of the media files to read.
    :type *urls: tuple(str)
    :param streams: list of file + stream specifiers or filtergraph label to output, alias of `map` option,
                    defaults to None, which outputs at most one video and one audio, selected by FFmpeg
    :type streams: seq(str), optional
    :param progress: progress callback function, defaults to None
    :type progress: callable object, optional
    :param show_log: True to show FFmpeg log messages on the console,
                     defaults to None (no show/capture)
                     Ignored if stream format must be retrieved automatically.
    :type show_log: bool, optional
    :param use_ya8: True if piped video streams uses `ya8` pix_fmt instead of `gray16le`, default to None
    :type use_ya8: bool, optional
    :param \\**options: FFmpeg options, append '_in[input_url_id]' for input option names for specific
                        input url or '_in' to be applied to all inputs. The url-specific option gets the
                        preference (see :doc:`options` for custom options)
    :type \\**options: dict, optional

    :return: frame rate and video frame data (dims: time x rows x cols x pix_comps)
    :rtype: (`fractions.Fraction`, `numpy.ndarray`)

    Note: Only pass in multiple urls to implement complex filtergraph. It's significantly faster to run
          `ffmpegio.video.read()` for each url.


    Unlike :py:mod:`video` and :py:mod:`image`, video pixel formats are not autodetected. If output
    'pix_fmt' option is not explicitly set, 'rgb24' is used.

    For audio streams, if 'sample_fmt' output option is not specified, 's16le'.


    streams = ['0:v:0','1:a:3'] # pick 1st file's 1st video stream and 2nd file's 4th audio stream

    """

    def __init__(self, *urls, streams=None, progress=None, show_log=None, blocksize=None, **options):

        self.dtype = None  # :numpy.dtype: output data type
        self.shape = (
            None  # :tuple of ints: dimension of each video frame or audio sample
        )
        self.itemsize = None  #:int: number of bytes of each video frame or audio sample
        self.blocksize = None  #:positive int: number of video frames or audio samples to read when used as an iterator

        # get url/file stream
        url, stdin, input = configure.check_url(url, False)

        input_options = utils.pop_extra_options(options, "_in")

        ffmpeg_args = configure.empty()
        configure.add_url(ffmpeg_args, "input", url, input_options)
        configure.add_url(ffmpeg_args, "output", "-", options)

        # abstract method to finalize the options => sets self.dtype and self.shape if known
        self._finalize(ffmpeg_args)

        # create logger without assigning the source stream
        self._logger = _LogerThread(None, show_log)

        # start FFmpeg
        self._proc = ffmpegprocess.Popen(
            ffmpeg_args,
            stdin=stdin,
            progress=progress,
            capture_log=True,
            close_stdin=True,
            close_stdout=False,
            close_stderr=False,
        )

        # set the log source and start the logger
        self._logger.stderr = self._proc.stderr
        self._logger.start()

        # if byte data is given, feed it
        if input is not None:
            self._proc.stdin.write(input)

        # wait until output stream log is captured if output format is unknown
        try:
            if self.dtype is None or self.shape is None:
                info = self._logger.output_stream()
                self._finalize_array(info)
            else:
                self._logger.index("Output")
        except:
            if self._proc.poll() is None:
                raise self._logger.Exception
            else:
                raise ValueError("failed retrieve output data format")

        self.itemsize = utils.get_itemsize(self.shape, self.dtype)

        self.blocksize = blocksize or max(1024 ** 2 // self.itemsize, 1)

    def close(self):
        """Flush and close this stream. This method has no effect if the stream is already
            closed. Once the stream is closed, any read operation on the stream will raise
            a ValueError.

        As a convenience, it is allowed to call this method more than once; only the first call,
        however, will have an effect.

        """
        self._proc.stdout.close()
        self._proc.stderr.close()
        try:
            self._proc.terminate()
        except:
            pass
        self._logger.join()

    @property
    def closed(self):
        """:bool: True if the stream is closed."""
        return self._proc.poll() is not None

    @property
    def lasterror(self):
        """:FFmpegError: Last error FFmpeg posted"""
        if self._proc.poll():
            return self._logger.Exception()
        else:
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self.read(self.blocksize)
        except:
            raise StopIteration

    def readlog(self, n=None):
        if n is not None:
            self._logger.index(n)
        with self._logger._newline_mutex:
            return "\n".join(self._logger.logs or self._logger.logs[:n])

    def read(self, n=-1):
        """Read and return numpy.ndarray with up to n frames/samples. If
        the argument is omitted, None, or negative, data is read and
        returned until EOF is reached. An empty bytes object is returned
        if the stream is already at EOF.

        If the argument is positive, and the underlying raw stream is not
        interactive, multiple raw reads may be issued to satisfy the byte
        count (unless EOF is reached first). But for interactive raw streams,
        at most one raw read will be issued, and a short result does not
        imply that EOF is imminent.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

        b = self._proc.stdout.read(n * self.itemsize if n > 0 else n)
        if not len(b):
            self._proc.stdout.close()
        return _as_array(b, self.shape, self.dtype)

    def readinto(self, array):
        """Read bytes into a pre-allocated, writable bytes-like object array and
        return the number of bytes read. For example, b might be a bytearray.

        Like read(), multiple reads may be issued to the underlying raw stream,
        unless the latter is interactive.

        A BlockingIOError is raised if the underlying raw stream is in non
        blocking-mode, and has no data available at the moment."""

        return self._proc.stdout.readinto(memoryview(array).cast("b")) // self.itemsize


class SimpleVideoReader(SimpleReaderBase):
    def _finalize(self, ffmpeg_args):
        # finalize FFmpeg arguments and output array

        inurl, inopts = ffmpeg_args.get("inputs", [])[0]
        outopts = ffmpeg_args.get("outputs", [])[0][1]
        has_fg = configure.has_filtergraph(ffmpeg_args, "video")

        pix_fmt = outopts.get("pix_fmt", None)
        if pix_fmt is None or (
            not has_fg
            and inurl not in ("-", "pipe:", "pipe:0")
            and not inopts.get("pix_fmt", None)
        ):
            # must assign output rgb/grayscale pixel format
            info = probe.video_streams_basic(inurl, 0)[0]
            pix_fmt_in = info["pix_fmt"]
            s_in = (info["width"], info["height"])
            r_in = info["frame_rate"]
        else:
            pix_fmt_in = s_in = r_in = None

        (
            self.dtype,
            self.shape,
            self.frame_rate,
        ) = configure.finalize_video_read_opts(ffmpeg_args, pix_fmt_in, s_in, r_in)

        # construct basic video filter if options specified
        configure.build_basic_vf(
            ffmpeg_args, utils.alpha_change(pix_fmt_in, pix_fmt, -1)
        )

    def _finalize_array(self, info):
        # finalize array setup from FFmpeg log

        self.frame_rate = info["r"]
        self.dtype, ncomp, _ = utils.get_video_format(info["pix_fmt"])
        self.shape = (*info["s"][::-1], ncomp)
