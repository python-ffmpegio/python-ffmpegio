# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0]

### Added

- `analyze` submodule to run frame-wise FFmpeg analysis filters
- `audio/detect` and `video/detect` as a convenient interface to `analyze` module

### Fixed

- `open()` handling of write mode
- 

## [0.5.0] - 2022-04-03

### Added

- `ffmpegio.ffmpeg` and `ffmpegio.ffprobe` functions to call `ffmpeg` & `ffprobe`, respectively,
  without any input argument processing
- `devices` submodule to provide a framework to enumerate I/O devices
- New `plugins` hooks: `device_source_api` and `device_sink_api`
- `plugins/devices/dshow` to support Windows' DirectShow device (`-f dshow`)
- `FFConcat` class to support `-f concat` demuxer and `ffconcat` auto-scripting
- `probe.frames` to retrieve frame information

### Fixed

- Fixed failed `import ffmpegio` when it cannot find FFmpeg binaries
- Many minor bugs

### Changed

- Uses `-hwaccel auto` as default for all inputs (experiment)
- Renamed `ffmpeg` module to `path`
- Refactored `probe.py` 

## [0.4.3] - 2022-03-02

### Fixed

- Fixed `path.find(ffmpeg_dir)` call

### Changed

- Renamed `path.get_ffmpeg` to `path.where`; original, `path.where` dropped

## [0.4.2] - 2022-02-27

### Fixed

- Fixed import failure if FFmpeg is not found in the system

### Changed

- Improved FFmpeg error reporting with `FFmpegError` exception
- `caps` functions nwo throw `FFmpegError` exceptions
- FFmpeg is called with `-nostdin` flag by default

### Added

- `ffmpegio.ffmpegprocess.FLAG` alias for `None` to make flag options more readable in `ffmpeg_args` dict

## [0.4.1] - 2022-02-22

### Fixed

- Fixed `caps` `ffmpeg` calls to print the banner 

## [0.4.0] - 2022-02-22

### Added

- `finder` plugin hook to allow custom automatic detection of ffmpeg executables

### Changed

- Major refactoring of supporting modules, including new `_utils` and `path` modules

### Fixed

- `-n` (no overwrite) global option is now used by default. Not having this caused
  the subprocess to hang, waiting for user input.

## [0.3.3] - 2022-02-17

### Fixed

- Fixed `pix_fmt` and `pix_fmt_in` check in `transcode` function

## [0.3.2] - 2022-02-17

### Fixed

- Fixed option handling bugs in `media` readers

### Added

- All readers to support `lavfi` source filter inputs

## [0.3.1] - 2022-02-15

### Fixed

- Output `image` dimension (v0.3.0 introduced a bug to return image as video frames)

### Changed

- `bytes_to_video` and `bytes_to_audio` plugin hooks to take additional argument `squeeze`

## [0.3.0] - 2022-02-13

### Changed

- Python distribution package name from `ffmpegio` to `ffmpegio-core`
- All raw data I/O operations are performed *without* NumPy array (NumPy support
  has been spun off to `python-ffmpegio-numpy` repo)
- `audio.create()` to return sampling rate and samples
- `ffmpegprocess.run()` to return its `stdout` output as `bytes`
- Updated AVI processing
- Cleaned up `SimpleStreams.py`
- All stream classes returns `rate` or `rate_in` (instead of `sample_rate` or `frame_rate`)
  
### Added

- Introduced plugin system (depending on `pluggy` package)

### Removed

- Removed acknowledging planar PCM `sample_fmt`'s

## [0.2.1] - 2022-02-01

### Added

- added 'rvv' & 'raa' open modes
- added secret bool option "_force_basic_vf"

### Fixed

- fixed: added media module to the root module
- fixed: exec() no longer sets stdin & stdout when unspecified
- fixed parse() handling of help options

### Changed

- ffmpeg.exec() capture_log option: None = console display, False = DEVNULL

## [0.2.0] - 2022-01-30

### Added

- added media.read()
- added streams.SimpleStreams.SimpleFilterBase
- added streams.SimpleStreams.SimpleAudioFilter
- added streams.SimpleStreams.SimpleVideoFilter
- added streams.AviStreams.AviMediaReader
- added 'vaf' and 'f' mode support for open()
- added ffmpegprocess.run_two_pass() for 2-pass encoding
- added 'two_pass', 'pass1_omits' and 'pass1_extras' arguments
  to video.write() and transcode()
- added threading.ReaderThread

### Changed

- moved and renamed ffmpeg.ProgressMonitor to threading.ProgressMonitorThread
- moved and renamed utils.log.Logger to threading.LoggerThread
- changed writer argument names

### Removed

- removed io.py and its dependencies

## [0.1.3] - 2022-01-26

### Added

- `square_pixels` options to video & image
- `overwrite` option to video and image stream writers
- `ffmpegprocess.Popen` to resolve misplaced global options

## [0.1.2] - 2022-01-23

### Added

- Added basic video filter options, incl. special handling of `s` output argument
  and autoconversion from transparent to opaque `pix_fmt` with `fill_color`
- Added `overwrite` argument to writer functions/classes
- `ffmpegprocess` submodule transports `PIPE` and `DEVNULL` from `subprocess`

### Changed

- `audio.create` `aframe` argument replaced with `t_in`
- `show_log` argument displays the log at the end even if log is captured
- Renamed `caps.pixfmts()` and `caps.samplefmts()` to `pix_fmts()` and `sample_fmts()`, respectively
- Split `caps.coders()` to `caps.decoders()` and `caps.encoders()`
- Several output dict key names changed in `caps` functions
  
### Removed

- Removed `progress` argument from all functions in `image` submodule
- Removed `utils.is_forced()`

### Fixed

- Fixed `caps._getCodecInfo` parsing issues

## [0.1.1] - 2022-01-21

### Added

- This file CHANGELOG
- `SimpleStreams.SimpleReaderBase.blocksize` property to specify the number of blocks of media data to read as iterator
  
### Changed

- Turned `SimpleStreams.SimpleReaderBase.readiter()` into `__iter__()` and `__next__()` to make the class Iterable
- Moved Github repo from `tikuma-lsuhsc` to `python-ffmpegio`
  
### Fixed

- Exception handling in `transcode.transcode()`

## [0.1.0] - 2022-01-20

### Added

- First beta release.
- Main functionality of `transcode`, `video`, `audio`, `image`, `SimpleStreams`, `probe`, and `caps` modules. 
- Preliminary implementations of `FilterGraph` and `FFmpegError` classes.

[Unreleased]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.4.3...v0.5.0
[0.4.3]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/92d467e...v0.1.0
