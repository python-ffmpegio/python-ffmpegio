# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- allow writers' `extra_inputs` arguments to be `str` or `tuple[str, dict|None]`

### Added

- `configure.add_urls()` to handle `extra_inputs` argument processing

### Fixed

- `probe._exec()` to decode the error message sent from ffprobe
- `filtergraph.Filter.add_labels()`: fixed a syntax error

## [0.10.0] - 2024-07-03

### Changed

- `caps` submodule - update format regex for v7 compatibility
- `filter` functions accept `expr=None` for implicit filters (e.g., reshape and resample)
- `probe.video/audio_stream_basic()`: added keep_str_values bool arg
- `probe._items_to_numeric()`: not convert hex values
- `probe`: added custom audio & video info probe functions - added `_audio_info()` and `_video_info()`
- `audio.read()` & `SimpleAudioReader`: switched to use `_audio_info()`
- `image.read()` `video.read()`, & `SimpleVideoReader`: switched to use `_video_info()`
- `probe`: `url` argument to support bytes-like object
- `probe._items_to_numeric()`: added to convert hex int and a:b ratio fraction
- `probe:_add_select_streams`: convert stream spec to str (if int)
- `probe`: added `keep_str_values` argument to ffprobe calling functions
- `probe`: added `keep_optional_fields` argument to ffprobe calling functions
- `probe`: added `sp_kwargs` argument to all ffprobe running functions
- `probe`: added `frames()` to `__all__`
- `open()`: major changes in input arguments
- `Filter` classes: Renamed constructor arguments
- `LoggerThread`: pass ffmpeg logs to debug log
- `open()`: no longer a context manager
- `Popen.send_signal`: defaults to perform ctrl-c
- `SimpleReaderBase.close`: poll before calling terminate

### Fixed

- `AviMediaReader`: fixed Issue #46 - a bug in `AviReaderThread.wait`
- `AviMediaReader`: fixed `__next__` behavior (now throws `StopIteration`)
- `AviReaderThread`: fixed buffer concatenation bug
- `compose_filter_args`: fixed escaping commas
- `probe._resolve_entries()`: fixed return value
- `probe.query`: fixed stream request id
- `probe`: fixed`cache_output=True` operation
- `probe.query()`: fixed a logic to return a single stream
- `probe:_add_show_entries`: fixed error if entries is bool
- `Popen`: fixed `progmon`'s cancel operation (ctrl-c)
- `ProgressMonitorThread`: call cancelfun() only once

### Removed

- `probe`: removed auto-caching ffprobe output
- 

## [0.9.1] - 2024-02-19

### Fixed

- `util.parser.compose`: fixed a bug composing FFmpeg arguments with an option with different values to two or more stream
- `streams.SimpleStreams.close`: prevent OSError even if pipes to ffmpeg process fail to close
- `threading.LoggerThread.run`: fixed to running logger thread when stderr not available
- `open` to convert unused rate argument to ffmpeg option

## [0.9.0] - 2023-12-08

### Changed

- No longer uses root logger. Creates and uses `"ffmpegio"` logger
- Tweaked to be compatible with FFmpeg v6.1
- Updated handling of repeated option values (overall + per-stream) so that per-stream value gets preference

## [0.8.6] - 2023-11-29

### Fixed

- `probe.query`: return only the requested fields when retrieving from a cached result
- `filtergraph`: can be imported even if ffmpeg executable is not present

### Changed

- `path.ffmpeg` & `path.ffprobe`: throw `FFmpegNotFound` if the executable not found

## [0.8.5] - 2023-11-13

### Changed

- `probe.query`: return a list of info of multiple streams if stream index is not specified
- `probe.query`: sped up querying specific fields (avoids full query)
- `probe.query`: no longer errors if a field is invalid

## [0.8.4] - 2023-11-07

### Added

- `transcode()` can output to `stdout`

### Fixed

- Fixed `show_log` handling in many functions

### Changed

- Dropped support for Python 3.7 but added 3.12
- Dropped setup.py. All setup metadata in `pyproject.toml`

## [0.8.3] - 2023-03-19

### Fixed

- SimpleStream writer/filter removed byte-casting of input buffer

## [0.8.2] - 2023-03-19

### Fixed

- `plugins.rawdata_bytes` casting `'buffers'` as `memoryview` has erroneous effect; now assume to receive `bytes`/`bytearray`

## [0.8.1] - 2023-03-18

### Fixed

- default plugins to return `None` if not compatible
- `analyze.BlurDetect.log` check `name` not `key`

## [0.8.0] - 2022-10-29

### Added

- `filtergraph` submodule for building complex filtergraphs
- `utils.parser.compose()` - support dict value for `-metadata` output option
- `sp_kwargs` argument to all the `read`, `write`, and `filter` functions and classes.

### Fixed

- `SimpleStreams.SimpleReaderBase.readinto()` - fixed plugin invocation bug
- added missing `show_log` argument to `image.filter()`

- `filtergraph` module with `Filter`, `Chain`, and `Graph` classes as FFmpeg filtergraph construction and manipulation tools
- `ffmpeg_ver` for easy access to linked FFmpeg version
- `FFmpegioError` exception class
- `utils.is_stream_spec`: new option `file_index=None` to search with or without filter index

### Changed

- consolidate representation of input/output/internal links for filtergraphs, affecting `util.filter.parse_graph()` & `util.filter.compose_graph()`
- corrected function names `util.*spec_stream` to `util.*stream_spec`
- `caps.filters()` outputs `FilterSummary` named tuple
- `caps.filter_info()` outputs `FilterInfo` named tuple
- `caps.filter_info()` outputs' `inputs` and `outputs` fields returns None if dynamic and [] if none
- `caps.filters()` outputs' `num_inputs` and `num_outputs` fields returns None if dynamic and 0 if none
- `FilterGraph` class is now redirected to the new `filtergraph.Graph`
- improved `audio.create()`, `image.create()`, and `video.create()`
- `configure.build_basic_vf()` to use `filtergraph.Graph` and can be appended to user specified `vf`
- `analyze` module, updated to use `filtergraph.Graph`
- `analyze.MetadataLogger`: changed `filter_spec` property to `filter` to return a `Filter` object
- moved `utils.error` module to `errors`
- `path.where()` to raise `FFmpegNotFound`

### Fixed

- `caps.filters()` - fixed reporting incorrect # of pads for source and sink filters
- `utils.parse_stream_spec()` - fixed file_index handling
- `utils.parse_stream_spec()` - fixed pid stream (`#`) regex
- `utils.filter` - fixed filter and filtergraph parsing bugs

## [0.7.0] - 2022-08-24

### Added

- `analysis` module to extract the frame metadata set by video/audio analysis filters
- `video.detect()` & `audio.detect()` to run the preset analyses
- `extra_inputs` argument to `audio.write`, `image.write`, `video.write`, and `SimpleWriterBase` constructor to support extra source urls
- `path.check_version()` to check FFmpeg version easily

### Fixed

- `util.concat`: Moved `FFConcat.options` to `FFConcat.File`. Removed `FFConcat.add_option()` and `FFConcat.add_options()`

## [0.6.0] - 2022-08-13

### Added

- Support for `gray10le`, `gray12le`, and `gray14le` pixel formats
- `ffmpegio.FFConcat.add_glob()` method

### Changed

- `SimpleReaderBase.read()` to return None if no frames remains

### Fixed

- BUG: `SimpleWriterBase.__next__()` returns empty frame at the eof
- BUG: `SimpleVideoReader` and `SimpleAudioReader` overwrites user specified options
- BUG: `SimpleWriterBase` fails to capture all the FFmpeg log lines

## [0.5.2] - 2022-06-18

### Fixed

- video writers hanging when a basic filter to remove alpha channel is used

### Changed

- `SimpleOutputStream`s output rates are now explicitly matched to input rates by default

## [0.5.1] - 2022-04-21

### Fixed

- `open()` handling of write mode

### Changed

- `probe` outputs Fraction for compatible entries

### Changed

- `transcode()` allowed to take multiple inputs or outputs

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
- All raw data I/O operations are performed _without_ NumPy array (NumPy support
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
- added secret bool option "\_force_basic_vf"

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

[unreleased]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.8.6...v0.9.0
[0.8.6]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.5.0...v0.5.1
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
