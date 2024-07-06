'''copied from MatplotLibe (the  main __init__.py)'''

__all__ = [
    "set_loglevel",
    "ExecutableNotFoundError",
    "get_configdir",
    "ffmpegio_fname",
    "FFmpegioDeprecationWarning",
    "RcParams",
    "rc_params",
    "rc_params_from_file",
    "rcParamsDefault",
    "rcParams",
    "rcParamsOrig",
    "defaultParams",
    "rc",
    "rcdefaults",
    "rc_file_defaults",
    "rc_file",
    "rc_context",
    "use",
    # "get_backend",
]


import atexit
from collections import namedtuple
from collections.abc import MutableMapping, MappingView
import contextlib
import functools
import locale
import logging
import os
from pathlib import Path
import pprint
import re
import shutil
import sys
import tempfile

from . import rcsetup
from .utils import _docstring

# cbook must import matplotlib only within function
# definitions, so it is safe to import from it here.
# from matplotlib import _api, _docstring
# from matplotlib._api import MatplotlibDeprecationWarning

# from matplotlib.rcsetup import validate_backend


_log = logging.getLogger(__name__)


# modelled after sys.version_info
_VersionInfo = namedtuple("_VersionInfo", "major, minor, micro, releaselevel, serial")


def sanitize_sequence(data):
    """
    Convert dictview objects to list. Other inputs are returned unchanged.
    """
    return list(data) if isinstance(data, MappingView) else data


# The decorator ensures this always returns the same handler (and it is only
# attached once).
@functools.cache
def _ensure_handler():
    """
    The first time this function is called, attach a `StreamHandler` using the
    same format as `logging.basicConfig` to the FFmpegIO root logger.

    Return this handler every time this function is called.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    _log.addHandler(handler)
    return handler


def set_loglevel(level):
    """
    Configure FFmpegIO's logging levels.

    FFmpegIO uses the standard library `logging` framework under the root
    logger 'ffmpegio'.  This is a helper function to:

    - set FFmpegIO's root logger level
    - set the root logger handler's level, creating the handler
      if it does not exist yet

    Typically, one should call ``set_loglevel("info")`` or
    ``set_loglevel("debug")`` to get additional debugging information.

    Users or applications that are installing their own logging handlers
    may want to directly manipulate ``logging.getLogger('ffmpegio')`` rather
    than use this function.

    Parameters
    ----------
    level : {"notset", "debug", "info", "warning", "error", "critical"}
        The log level of the handler.

    Notes
    -----
    The first time this function is called, an additional handler is attached
    to FFmpegIO's root handler; this handler is reused every time and this
    function simply manipulates the logger and handler's level.

    """
    _log.setLevel(level.upper())
    _ensure_handler().setLevel(level.upper())


def _logged_cached(fmt, func=None):
    """
    Decorator that logs a function's return value, and memoizes that value.

    After ::

        @_logged_cached(fmt)
        def func(): ...

    the first call to *func* will log its return value at the DEBUG level using
    %-format string *fmt*, and memoize it; later calls to *func* will directly
    return that value.
    """
    if func is None:  # Return the actual decorator.
        return functools.partial(_logged_cached, fmt)

    called = False
    ret = None

    @functools.wraps(func)
    def wrapper(**kwargs):
        nonlocal called, ret
        if not called:
            ret = func(**kwargs)
            called = True
            _log.debug(fmt, ret)
        return ret

    return wrapper


_ExecInfo = namedtuple("_ExecInfo", "executable raw_version version")


class ExecutableNotFoundError(FileNotFoundError):
    """
    Error raised when an FFmpeg executable can't be found.
    """

    pass


def _get_xdg_config_dir():
    """
    Return the XDG configuration directory, according to the XDG base
    directory spec:

    https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
    """
    return os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")


def _get_xdg_cache_dir():
    """
    Return the XDG cache directory, according to the XDG base directory spec:

    https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
    """
    return os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")


def _get_config_or_cache_dir(xdg_base_getter):
    configdir = os.environ.get("FFMPEGIOCONFIGDIR")
    if configdir:
        configdir = Path(configdir).resolve()
    elif sys.platform.startswith(("linux", "freebsd")):
        # Only call _xdg_base_getter here so that FFMPEGIOCONFIGDIR is tried first,
        # as _xdg_base_getter can throw.
        configdir = Path(xdg_base_getter(), "ffmpegio")
    else:
        configdir = Path.home() / ".ffmpegio"
    try:
        configdir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    else:
        if os.access(str(configdir), os.W_OK) and configdir.is_dir():
            return str(configdir)
    # If the config or cache directory cannot be created or is not a writable
    # directory, create a temporary one.
    try:
        tmpdir = tempfile.mkdtemp(prefix="ffmpegio-")
    except OSError as exc:
        raise OSError(
            f"FFmpegio requires access to a writable cache directory, but the "
            f"default path ({configdir}) is not a writable directory, and a temporary "
            f"directory could not be created; set the FFMPEGIOCONFIGDIR environment "
            f"variable to a writable directory"
        ) from exc
    os.environ["FFMPEGIOCONFIGDIR"] = tmpdir
    atexit.register(shutil.rmtree, tmpdir)
    _log.warning(
        "FFmpegIO created a temporary cache directory at %s because the default path "
        "(%s) is not a writable directory; it is highly recommended to set the "
        "FFMPEGIOCONFIGDIR environment variable to a writable directory, in particular to "
        "speed up the import of FFmpegIO and to better support multiprocessing.",
        tmpdir,
        configdir,
    )
    return tmpdir


@_logged_cached("CONFIGDIR=%s")
def get_configdir():
    """
    Return the string path of the configuration directory.

    The directory is chosen as follows:

    1. If the FFMPEGIOCONFIGDIR environment variable is supplied, choose that.
    2. On Linux, follow the XDG specification and look first in
       ``$XDG_CONFIG_HOME``, if defined, or ``$HOME/.config``.  On other
       platforms, choose ``$HOME/.ffmpegio``.
    3. If the chosen directory exists and is writable, use that as the
       configuration directory.
    4. Else, create a temporary directory, and use it as the configuration
       directory.
    """
    return _get_config_or_cache_dir(_get_xdg_config_dir)


@_logged_cached("CACHEDIR=%s")
def get_cachedir():
    """
    Return the string path of the cache directory.

    The procedure used to find the directory is the same as for
    `get_configdir`, except using ``$XDG_CACHE_HOME``/``$HOME/.cache`` instead.
    """
    return _get_config_or_cache_dir(_get_xdg_cache_dir)


@_logged_cached("ffmpegio data path: %s")
def get_data_path():
    """Return the path to FFmpegIO data."""
    return str(Path(__file__).with_name("ffmpegio-data"))


def _get_data_path(*args):
    """
    Return the `pathlib.Path` to a resource file provided by Matplotlib.

    ``*args`` specify a path relative to the base data path.
    """
    return Path(get_data_path(), *args)


def matplotlib_fname():
    """
    Get the location of the config file.

    The file location is determined in the following order

    - ``$PWD/ffmpegiorc``
    - ``$FFMPEGIORC`` if it is not a directory
    - ``$FFMPEGIORC/ffmpegiorc``
    - ``$FFMPEGIOCONFIGDIR/ffmpegiorc``
    - On Linux,
        - ``$XDG_CONFIG_HOME/ffmpegio/ffmpegiorc`` (if ``$XDG_CONFIG_HOME``
          is defined)
        - or ``$HOME/.config/ffmpegio/ffmpegiorc`` (if ``$XDG_CONFIG_HOME``
          is not defined)
    - On other platforms,
      - ``$HOME/.ffmpegio/ffmpegiorc`` if ``$HOME`` is defined
    - Lastly, it looks in ``$FFMPEGIODATA/ffmpegiorc``, which should always
      exist.
    """

    def gen_candidates():
        # rely on down-stream code to make absolute.  This protects us
        # from having to directly get the current working directory
        # which can fail if the user has ended up with a cwd that is
        # non-existent.
        yield "ffmpegiorc"
        try:
            ffmpegiorc = os.environ["FFMPEGIORC"]
        except KeyError:
            pass
        else:
            yield ffmpegiorc
            yield os.path.join(ffmpegiorc, "ffmpegiorc")
        yield os.path.join(get_configdir(), "ffmpegiorc")
        yield os.path.join(get_data_path(), "ffmpegiorc")

    for fname in gen_candidates():
        if os.path.exists(fname) and not os.path.isdir(fname):
            return fname

    raise RuntimeError(
        "Could not find ffmpegiorc file; your FFmpegIO " "install is broken"
    )


# rcParams deprecated and automatically mapped to another key.
# Values are tuples of (version, new_name, f_old2new, f_new2old).
_deprecated_map = {}
# rcParams deprecated; some can manually be mapped to another key.
# Values are tuples of (version, new_name_or_None).
_deprecated_ignore_map = {}
# rcParams deprecated; can use None to suppress warnings; remain actually
# listed in the rcParams.
# Values are tuples of (version,)
_deprecated_remain_as_none = {}


# @_docstring.Substitution(
#     "\n".join(map("- {}".format, sorted(rcsetup._validators, key=str.lower)))
# )
class RcParams(MutableMapping, dict):
    """
    A dict-like key-value store for config parameters, including validation.

    Validating functions are defined and associated with rc parameters in
    :mod:`ffmpegio.rcsetup`.

    The list of rcParams is:

    %s

    See Also
    --------
    :ref:`customizing-with-ffmpegiorc-files`
    """

    validate = rcsetup._validators

    # validate values on the way in
    def __init__(self, *args, **kwargs):
        self.update(*args, **kwargs)

    def _set(self, key, val):
        """
        Directly write data bypassing deprecation and validation logic.

        Notes
        -----
        As end user or downstream library you almost always should use
        ``rcParams[key] = val`` and not ``_set()``.

        There are only very few special cases that need direct data access.
        These cases previously used ``dict.__setitem__(rcParams, key, val)``,
        which is now deprecated and replaced by ``rcParams._set(key, val)``.

        Even though private, we guarantee API stability for ``rcParams._set``,
        i.e. it is subject to FFmpegIO's API and deprecation policy.

        :meta public:
        """
        dict.__setitem__(self, key, val)

    def _get(self, key):
        """
        Directly read data bypassing deprecation, backend and validation
        logic.

        Notes
        -----
        As end user or downstream library you almost always should use
        ``val = rcParams[key]`` and not ``_get()``.

        There are only very few special cases that need direct data access.
        These cases previously used ``dict.__getitem__(rcParams, key, val)``,
        which is now deprecated and replaced by ``rcParams._get(key)``.

        Even though private, we guarantee API stability for ``rcParams._get``,
        i.e. it is subject to FFmpegIO's API and deprecation policy.

        :meta public:
        """
        return dict.__getitem__(self, key)

    def __setitem__(self, key, val):
        try:
            # if key in _deprecated_map:
            #     version, alt_key, alt_val, inverse_alt = _deprecated_map[key]
            #     _api.warn_deprecated(
            #         version, name=key, obj_type="rcparam", alternative=alt_key
            #     )
            #     key = alt_key
            #     val = alt_val(val)
            # elif key in _deprecated_remain_as_none and val is not None:
            #     (version,) = _deprecated_remain_as_none[key]
            #     _api.warn_deprecated(version, name=key, obj_type="rcparam")
            # elif key in _deprecated_ignore_map:
            #     version, alt_key = _deprecated_ignore_map[key]
            #     _api.warn_deprecated(
            #         version, name=key, obj_type="rcparam", alternative=alt_key
            #     )
            #     return
            # el
            if key == "backend":
                if val is rcsetup._auto_backend_sentinel:
                    if "backend" in self:
                        return
            try:
                cval = self.validate[key](val)
            except ValueError as ve:
                raise ValueError(f"Key {key}: {ve}") from None
            self._set(key, cval)
        except KeyError as err:
            raise KeyError(
                f"{key} is not a valid rc parameter (see rcParams.keys() for "
                f"a list of valid parameters)"
            ) from err

    def __getitem__(self, key):
        if key in _deprecated_map:
            version, alt_key, alt_val, inverse_alt = _deprecated_map[key]
            # _api.warn_deprecated(
            #     version, name=key, obj_type="rcparam", alternative=alt_key
            # )
            return inverse_alt(self._get(alt_key))

        elif key in _deprecated_ignore_map:
            version, alt_key = _deprecated_ignore_map[key]
            # _api.warn_deprecated(
            #     version, name=key, obj_type="rcparam", alternative=alt_key
            # )
            return self._get(alt_key) if alt_key else None

        # In theory, this should only ever be used after the global rcParams
        # has been set up, but better be safe e.g. in presence of breakpoints.
        elif key == "backend" and self is globals().get("rcParams"):
            val = self._get(key)
            if val is rcsetup._auto_backend_sentinel:
                from matplotlib import pyplot as plt

                plt.switch_backend(rcsetup._auto_backend_sentinel)

        return self._get(key)

    def _get_backend_or_none(self):
        """Get the requested backend, if any, without triggering resolution."""
        backend = self._get("backend")
        return None if backend is rcsetup._auto_backend_sentinel else backend

    def __repr__(self):
        class_name = self.__class__.__name__
        indent = len(class_name) + 1
        # with _api.suppress_matplotlib_deprecation_warning():
        repr_split = pprint.pformat(dict(self), indent=1, width=80 - indent).split(
            "\n"
        )
        repr_indented = ("\n" + " " * indent).join(repr_split)
        return f"{class_name}({repr_indented})"

    def __str__(self):
        return "\n".join(map("{0[0]}: {0[1]}".format, sorted(self.items())))

    def __iter__(self):
        """Yield sorted list of keys."""
        # with _api.suppress_matplotlib_deprecation_warning():
        yield from sorted(dict.__iter__(self))

    def __len__(self):
        return dict.__len__(self)

    def find_all(self, pattern):
        """
        Return the subset of this RcParams dictionary whose keys match,
        using :func:`re.search`, the given ``pattern``.

        .. note::

            Changes to the returned dictionary are *not* propagated to
            the parent RcParams dictionary.

        """
        pattern_re = re.compile(pattern)
        return RcParams(
            (key, value) for key, value in self.items() if pattern_re.search(key)
        )

    def copy(self):
        """Copy this RcParams instance."""
        rccopy = RcParams()
        for k in self:  # Skip deprecations and revalidation.
            rccopy._set(k, self._get(k))
        return rccopy


def rc_params(fail_on_error=False):
    """Construct a `RcParams` instance from the default FFmpegIO rc file."""
    return rc_params_from_file(matplotlib_fname(), fail_on_error)


@functools.cache
def _get_ssl_context():
    try:
        import certifi
    except ImportError:
        _log.debug("Could not import certifi.")
        return None
    import ssl

    return ssl.create_default_context(cafile=certifi.where())


@contextlib.contextmanager
def _open_file_or_url(fname):
    if isinstance(fname, str) and fname.startswith(
        ("http://", "https://", "ftp://", "file:")
    ):
        import urllib.request

        ssl_ctx = _get_ssl_context()
        if ssl_ctx is None:
            _log.debug("Could not get certifi ssl context, https may not work.")
        with urllib.request.urlopen(fname, context=ssl_ctx) as f:
            yield (line.decode("utf-8") for line in f)
    else:
        fname = os.path.expanduser(fname)
        with open(fname, encoding="utf-8") as f:
            yield f


def _strip_comment(s):
    """Strip everything from the first unquoted #."""
    pos = 0
    while True:
        quote_pos = s.find('"', pos)
        hash_pos = s.find("#", pos)
        if quote_pos < 0:
            without_comment = s if hash_pos < 0 else s[:hash_pos]
            return without_comment.strip()
        elif 0 <= hash_pos < quote_pos:
            return s[:hash_pos].strip()
        else:
            closing_quote_pos = s.find('"', quote_pos + 1)
            if closing_quote_pos < 0:
                raise ValueError(
                    f"Missing closing quote in: {s!r}. If you need a double-"
                    'quote inside a string, use escaping: e.g. "the " char"'
                )
            pos = closing_quote_pos + 1  # behind closing quote


def _rc_params_in_file(fname, transform=lambda x: x, fail_on_error=False):
    """
    Construct a `RcParams` instance from file *fname*.

    Unlike `rc_params_from_file`, the configuration class only contains the
    parameters specified in the file (i.e. default values are not filled in).

    Parameters
    ----------
    fname : path-like
        The loaded file.
    transform : callable, default: the identity function
        A function called on each individual line of the file to transform it,
        before further parsing.
    fail_on_error : bool, default: False
        Whether invalid entries should result in an exception or a warning.
    """
    import ffmpegio as ff

    rc_temp = {}
    with _open_file_or_url(fname) as fd:
        try:
            for line_no, line in enumerate(fd, 1):
                line = transform(line)
                strippedline = _strip_comment(line)
                if not strippedline:
                    continue
                tup = strippedline.split(":", 1)
                if len(tup) != 2:
                    _log.warning(
                        "Missing colon in file %r, line %d (%r)",
                        fname,
                        line_no,
                        line.rstrip("\n"),
                    )
                    continue
                key, val = tup
                key = key.strip()
                val = val.strip()
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]  # strip double quotes
                if key in rc_temp:
                    _log.warning(
                        "Duplicate key in file %r, line %d (%r)",
                        fname,
                        line_no,
                        line.rstrip("\n"),
                    )
                rc_temp[key] = (val, line, line_no)
        except UnicodeDecodeError:
            _log.warning("Cannot decode configuration file %r as utf-8.", fname)
            raise

    config = RcParams()

    for key, (val, line, line_no) in rc_temp.items():
        if key in rcsetup._validators:
            if fail_on_error:
                config[key] = val  # try to convert to proper type or raise
            else:
                try:
                    config[key] = val  # try to convert to proper type or skip
                except Exception as msg:
                    _log.warning(
                        "Bad value in file %r, line %d (%r): %s",
                        fname,
                        line_no,
                        line.rstrip("\n"),
                        msg,
                    )
        # elif key in _deprecated_ignore_map:
        #     version, alt_key = _deprecated_ignore_map[key]
        #     _api.warn_deprecated(
        #         version,
        #         name=key,
        #         alternative=alt_key,
        #         obj_type="rcparam",
        #         addendum="Please update your ffmpegiorc.",
        #     )
        else:
            # __version__ must be looked up as an attribute to trigger the
            # module-level __getattr__.
            version = "main" if ".post" in ff.__version__ else f"v{ff.__version__}"
            _log.warning(
                """
Bad key %(key)s in file %(fname)s, line %(line_no)s (%(line)r)
You probably need to get an updated ffmpegiorc file from
https://github.com/ffmpegio/ffmpegio/blob/%(version)s/lib/ffmpegio/ffmpegio-data/ffmpegiorc
or from the ffmpegio source distribution""",
                dict(
                    key=key,
                    fname=fname,
                    line_no=line_no,
                    line=line.rstrip("\n"),
                    version=version,
                ),
            )
    return config


def rc_params_from_file(fname, fail_on_error=False, use_default_template=True):
    """
    Construct a `RcParams` from file *fname*.

    Parameters
    ----------
    fname : str or path-like
        A file with FFmpegIO rc settings.
    fail_on_error : bool
        If True, raise an error when the parser fails to convert a parameter.
    use_default_template : bool
        If True, initialize with default parameters before updating with those
        in the given file. If False, the configuration class only contains the
        parameters specified in the file. (Useful for updating dicts.)
    """
    config_from_file = _rc_params_in_file(fname, fail_on_error=fail_on_error)

    if not use_default_template:
        return config_from_file

    # with _api.suppress_matplotlib_deprecation_warning():
    config = RcParams({**rcParamsDefault, **config_from_file})

    _log.debug("loaded rc file %s", fname)

    return config


# When constructing the global instances, we need to perform certain updates
# by explicitly calling the superclass (dict.update, dict.items) to avoid
# triggering resolution of _auto_backend_sentinel.
rcParamsDefault = _rc_params_in_file(
    _get_data_path("ffmpegiorc"),
    # Strip leading comment.
    transform=lambda line: line[1:] if line.startswith("#") else line,
    fail_on_error=True,
)
dict.update(rcParamsDefault, rcsetup._hardcoded_defaults)
# Normally, the default ffmpegiorc file contains *no* entry for backend (the
# corresponding line starts with ##, not #; we fill on _auto_backend_sentinel
# in that case.  However, packagers can set a different default backend
# (resulting in a normal `#backend: foo` line) in which case we should *not*
# fill in _auto_backend_sentinel.
dict.setdefault(rcParamsDefault, "backend", rcsetup._auto_backend_sentinel)
rcParams = RcParams()  # The global instance.
dict.update(rcParams, dict.items(rcParamsDefault))
dict.update(rcParams, _rc_params_in_file(matplotlib_fname()))
rcParamsOrig = rcParams.copy()
# with _api.suppress_matplotlib_deprecation_warning():
# This also checks that all rcParams are indeed listed in the template.
# Assigning to rcsetup.defaultParams is left only for backcompat.
defaultParams = rcsetup.defaultParams = {
    # We want to resolve deprecated rcParams, but not backend...
    key: [
        (
            rcsetup._auto_backend_sentinel
            if key == "backend"
            else rcParamsDefault[key]
        ),
        validator,
    ]
    for key, validator in rcsetup._validators.items()
}


def rc(group, **kwargs):
    """
    Set the current `.rcParams`.  *group* is the grouping for the rc, e.g.,
    for ``lines.linewidth`` the group is ``lines``, for
    ``axes.facecolor``, the group is ``axes``, and so on.  Group may
    also be a list or tuple of group names, e.g., (*xtick*, *ytick*).
    *kwargs* is a dictionary attribute name/value pairs, e.g.,::

      rc('lines', linewidth=2, color='r')

    sets the current `.rcParams` and is equivalent to::

      rcParams['lines.linewidth'] = 2
      rcParams['lines.color'] = 'r'

    The following aliases are available to save typing for interactive users:

    =====   =================
    Alias   Property
    =====   =================
    'lw'    'linewidth'
    'ls'    'linestyle'
    'c'     'color'
    'fc'    'facecolor'
    'ec'    'edgecolor'
    'mew'   'markeredgewidth'
    'aa'    'antialiased'
    =====   =================

    Thus you could abbreviate the above call as::

          rc('lines', lw=2, c='r')

    Note you can use python's kwargs dictionary facility to store
    dictionaries of default parameters.  e.g., you can customize the
    font rc as follows::

      font = {'family' : 'monospace',
              'weight' : 'bold',
              'size'   : 'larger'}
      rc('font', **font)  # pass in the font dict as kwargs

    This enables you to easily switch between several configurations.  Use
    ``ffmpegio.style.use('default')`` or :func:`~ffmpegio.rcdefaults` to
    restore the default `.rcParams` after changes.

    Notes
    -----
    Similar functionality is available by using the normal dict interface, i.e.
    ``rcParams.update({"lines.linewidth": 2, ...})`` (but ``rcParams.update``
    does not support abbreviations or grouping).
    """

    aliases = {
        # "lw": "linewidth",
    }

    if isinstance(group, str):
        group = (group,)
    for g in group:
        for k, v in kwargs.items():
            name = aliases.get(k) or k
            key = f"{g}.{name}"
            try:
                rcParams[key] = v
            except KeyError as err:
                raise KeyError(
                    ('Unrecognized key "%s" for group "%s" and ' 'name "%s"')
                    % (key, g, name)
                ) from err


def rcdefaults():
    """
    Restore the `.rcParams` from FFmpegIO's internal default style.

    Style-blacklisted `.rcParams` (defined in
    ``ffmpegio.style.core.STYLE_BLACKLIST``) are not updated.

    See Also
    --------
    ffmpegio.rc_file_defaults
        Restore the `.rcParams` from the rc file originally loaded by
        FFmpegIO.
    ffmpegio.style.use
        Use a specific style file.  Call ``style.use('default')`` to restore
        the default style.
    """
    # Deprecation warnings were already handled when creating rcParamsDefault,
    # no need to reemit them here.
    # with _api.suppress_matplotlib_deprecation_warning():
        # from .style.core import STYLE_BLACKLIST

    rcParams.clear()
    rcParams.update(
        {k: v for k, v in rcParamsDefault.items() }#if k not in STYLE_BLACKLIST}
    )


def rc_file_defaults():
    """
    Restore the `.rcParams` from the original rc file loaded by FFmpegIO.

    Style-blacklisted `.rcParams` (defined in
    ``ffmpegio.style.core.STYLE_BLACKLIST``) are not updated.
    """
    # Deprecation warnings were already handled when creating rcParamsOrig, no
    # need to reemit them here.
    # with _api.suppress_matplotlib_deprecation_warning():
        # from .style.core import STYLE_BLACKLIST

    rcParams.update(
        {k: rcParamsOrig[k] for k in rcParamsOrig }#if k not in STYLE_BLACKLIST}
    )


def rc_file(fname, *, use_default_template=True):
    """
    Update `.rcParams` from file.

    Style-blacklisted `.rcParams` (defined in
    ``ffmpegio.style.core.STYLE_BLACKLIST``) are not updated.

    Parameters
    ----------
    fname : str or path-like
        A file with FFmpegIO rc settings.

    use_default_template : bool
        If True, initialize with default parameters before updating with those
        in the given file. If False, the current configuration persists
        and only the parameters specified in the file are updated.
    """
    # Deprecation warnings were already handled in rc_params_from_file, no need
    # to reemit them here.
    # with _api.suppress_matplotlib_deprecation_warning():
    #     from .style.core import STYLE_BLACKLIST

    rc_from_file = rc_params_from_file(
        fname, use_default_template=use_default_template
    )
    rcParams.update(
        {k: rc_from_file[k] for k in rc_from_file }#if k not in STYLE_BLACKLIST}
    )


@contextlib.contextmanager
def rc_context(rc=None, fname=None):
    """
    Return a context manager for temporarily changing rcParams.

    The :rc:`backend` will not be reset by the context manager.

    rcParams changed both through the context manager invocation and
    in the body of the context will be reset on context exit.

    Parameters
    ----------
    rc : dict
        The rcParams to temporarily set.
    fname : str or path-like
        A file with FFmpegIO rc settings. If both *fname* and *rc* are given,
        settings from *rc* take precedence.

    See Also
    --------
    :ref:`customizing-with-ffmpegiorc-files`

    Examples
    --------
    Passing explicit values via a dict::

        with ff.rc_context({'interactive': False}):
            fig, ax = plt.subplots()
            ax.plot(range(3), range(3))
            fig.savefig('example.png')
            plt.close(fig)

    Loading settings from a file::

         with ff.rc_context(fname='print.rc'):
             plt.plot(x, y)  # uses 'print.rc'

    Setting in the context body::

        with ff.rc_context():
            # will be reset
            ff.rcParams['lines.linewidth'] = 5
            plt.plot(x, y)

    """
    orig = dict(rcParams.copy())
    del orig["backend"]
    try:
        if fname:
            rc_file(fname)
        if rc:
            rcParams.update(rc)
        yield
    finally:
        dict.update(rcParams, orig)  # Revert to the original rcs.


def use(backend, *, force=True):
    """
    Select the backend used for rendering and GUI integration.

    If pyplot is already imported, `~ffmpegio.pyplot.switch_backend` is used
    and if the new backend is different than the current backend, all Figures
    will be closed.

    Parameters
    ----------
    backend : str
        The backend to switch to.  This can either be one of the standard
        backend names, which are case-insensitive:

        - interactive backends:
          GTK3Agg, GTK3Cairo, GTK4Agg, GTK4Cairo, MacOSX, nbAgg, notebook, QtAgg,
          QtCairo, TkAgg, TkCairo, WebAgg, WX, WXAgg, WXCairo, Qt5Agg, Qt5Cairo

        - non-interactive backends:
          agg, cairo, pdf, pgf, ps, svg, template

        or a string of the form: ``module://my.module.name``.

        notebook is a synonym for nbAgg.

        Switching to an interactive backend is not possible if an unrelated
        event loop has already been started (e.g., switching to GTK3Agg if a
        TkAgg window has already been opened).  Switching to a non-interactive
        backend is always possible.

    force : bool, default: True
        If True (the default), raise an `ImportError` if the backend cannot be
        set up (either because it fails to import, or because an incompatible
        GUI interactive framework is already running); if False, silently
        ignore the failure.

    See Also
    --------
    :ref:`backends`
    ffmpegio.get_backend
    ffmpegio.pyplot.switch_backend

    """
    name = validate_backend(backend)
    # don't (prematurely) resolve the "auto" backend setting
    if rcParams._get_backend_or_none() == name:
        # Nothing to do if the requested backend is already set
        pass
    else:
        # if pyplot is not already imported, do not import it.  Doing
        # so may trigger a `plt.switch_backend` to the _default_ backend
        # before we get a chance to change to the one the user just requested
        plt = sys.modules.get("ffmpegio.pyplot")
        # if pyplot is imported, then try to change backends
        if plt is not None:
            try:
                # we need this import check here to re-raise if the
                # user does not have the libraries to support their
                # chosen backend installed.
                plt.switch_backend(name)
            except ImportError:
                if force:
                    raise
        # if we have not imported pyplot, then we can set the rcParam
        # value which will be respected when the user finally imports
        # pyplot
        else:
            rcParams["backend"] = backend
    # if the user has asked for a given backend, do not helpfully
    # fallback
    rcParams["backend_fallback"] = False


if os.environ.get("MPLBACKEND"):
    rcParams["backend"] = os.environ.get("MPLBACKEND")


def get_backend():
    """
    Return the name of the current backend.

    See Also
    --------
    ffmpegio.use
    """
    return rcParams["backend"]


def _val_or_rc(val, rc_name):
    """
    If *val* is None, return ``ff.rcParams[rc_name]``, otherwise return val.
    """
    return val if val is not None else rcParams[rc_name]


_log.debug("platform is %s", sys.platform)
