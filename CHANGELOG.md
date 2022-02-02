# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1]

### Added

-added 'rvv' & 'raa' open modes
-added secret bool option "_force_basic_vf"

### Fixed

-fixed: added media module to the root module
-fixed: exec() no longer sets stdin & stdout when unspecified
-fixed parse() handling of help options

### Changed

-ffmpeg.exec() capture_log option: None = console display, False = DEVNULL

## [0.2.0]

### Added
-added media.read()
-added streams.SimpleStreams.SimpleFilterBase
-added streams.SimpleStreams.SimpleAudioFilter
-added streams.SimpleStreams.SimpleVideoFilter
-added streams.AviStreams.AviMediaReader
-added 'vaf' and 'f' mode support for open()
-added ffmpegprocess.run_two_pass() for 2-pass encoding
-added 'two_pass', 'pass1_omits' and 'pass1_extras' arguments
 to video.write() and transcode()
-added threading.ReaderThread

### Changed

- moved and renamed ffmpeg.ProgressMonitor to threading.ProgressMonitorThread
- moved and renamed utils.log.Logger to threading.LoggerThread
- changed writer argument names

### Removed

    -removed io.py and its dependencies

## [0.1.3]

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

[Unreleased]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/92d467e...v0.1.0
