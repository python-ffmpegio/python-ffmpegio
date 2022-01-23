# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]
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

[Unreleased]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/python-ffmpegio/python-ffmpegio/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/python-ffmpegio/python-ffmpegio/compare/92d467e...v0.1.0
