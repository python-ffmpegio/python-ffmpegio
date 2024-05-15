__all__ = [
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
]


import atexit
from collections.abc import MutableMapping
import contextlib
import functools
import inspect
from inspect import Parameter
import locale
import logging
import os
from pathlib import Path
import pprint
import re
import shutil
import sys
import tempfile
import collections
import inspect

from . import rcsetup

_log = logging.getLogger(__name__)

# from matplotlib import pyplot, cbook

class Substitution:
    """
    A decorator that performs %-substitution on an object's docstring.

    This decorator should be robust even if ``obj.__doc__`` is None (for
    example, if -OO was passed to the interpreter).

    Usage: construct a docstring.Substitution with a sequence or dictionary
    suitable for performing substitution; then decorate a suitable function
    with the constructed object, e.g.::

        sub_author_name = Substitution(author='Jason')

        @sub_author_name
        def some_function(x):
            "%(author)s wrote this function"

        # note that some_function.__doc__ is now "Jason wrote this function"

    One can also use positional arguments::

        sub_first_last_names = Substitution('Edgar Allen', 'Poe')

        @sub_first_last_names
        def some_function(x):
            "%s %s wrote the Raven"

    ref: a copy of matplotlib._docstring.Substitution
    """

    def __init__(self, *args, **kwargs):
        if args and kwargs:
            raise TypeError("Only positional or keyword args are allowed")
        self.params = args or kwargs

    def __call__(self, func):
        if func.__doc__:
            func.__doc__ = inspect.cleandoc(func.__doc__) % self.params
        return func

    def update(self, *args, **kwargs):
        """
        Update ``self.params`` (which must be a dict) with the supplied args.
        """
        self.params.update(*args, **kwargs)


def sanitize_sequence(data):
    """
    Convert dictview objects to list. Other inputs are returned unchanged.

    [from matplotlib.cbook]
    """
    return list(data) if isinstance(data, collections.abc.MappingView) else data


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
    configdir = os.environ.get("MPLCONFIGDIR")
    if configdir:
        configdir = Path(configdir).resolve()
    elif sys.platform.startswith(("linux", "freebsd")):
        # Only call _xdg_base_getter here so that MPLCONFIGDIR is tried first,
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
            f"Matplotlib requires access to a writable cache directory, but the "
            f"default path ({configdir}) is not a writable directory, and a temporary "
            f"directory could not be created; set the MPLCONFIGDIR environment "
            f"variable to a writable directory"
        ) from exc
    os.environ["MPLCONFIGDIR"] = tmpdir
    atexit.register(shutil.rmtree, tmpdir)
    _log.warning(
        "Matplotlib created a temporary cache directory at %s because the default path "
        "(%s) is not a writable directory; it is highly recommended to set the "
        "MPLCONFIGDIR environment variable to a writable directory, in particular to "
        "speed up the import of Matplotlib and to better support multiprocessing.",
        tmpdir,
        configdir,
    )
    return tmpdir


@_logged_cached("CONFIGDIR=%s")
def get_configdir():
    """
    Return the string path of the configuration directory.

    The directory is chosen as follows:

    1. If the MPLCONFIGDIR environment variable is supplied, choose that.
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
    """Return the path to Matplotlib data."""
    return str(Path(__file__).with_name("ffio-data"))


def ffmpegio_fname():
    """
    Get the location of the config file.

    The file location is determined in the following order

    - ``$PWD/ffmpegiorc``
    - ``$MATPLOTLIBRC`` if it is not a directory
    - ``$MATPLOTLIBRC/ffmpegiorc``
    - ``$MPLCONFIGDIR/ffmpegiorc``
    - On Linux,
        - ``$XDG_CONFIG_HOME/ffmpegio/ffmpegiorc`` (if ``$XDG_CONFIG_HOME``
          is defined)
        - or ``$HOME/.config/ffmpegio/ffmpegiorc`` (if ``$XDG_CONFIG_HOME``
          is not defined)
    - On other platforms,
      - ``$HOME/.ffmpegio/ffmpegiorc`` if ``$HOME`` is defined
    - Lastly, it looks in ``$MATPLOTLIBDATA/ffmpegiorc``, which should always
      exist.
    """

    def gen_candidates():
        # rely on down-stream code to make absolute.  This protects us
        # from having to directly get the current working directory
        # which can fail if the user has ended up with a cwd that is
        # non-existent.
        yield "ffmpegiorc"
        try:
            ffmpegiorc = os.environ["MATPLOTLIBRC"]
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
        "Could not find ffmpegiorc file; your Matplotlib " "install is broken"
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


@Substitution("\n".join(map("- {}".format, sorted(rcsetup._validators, key=str.lower))))
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
        i.e. it is subject to Matplotlib's API and deprecation policy.

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
        i.e. it is subject to ffmpegio's API and deprecation policy.

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
        # if key in _deprecated_map:
        #     version, alt_key, alt_val, inverse_alt = _deprecated_map[key]
        #     _api.warn_deprecated(
        #         version, name=key, obj_type="rcparam", alternative=alt_key
        #     )
        #     return inverse_alt(self._get(alt_key))

        # elif key in _deprecated_ignore_map:
        #     version, alt_key = _deprecated_ignore_map[key]
        #     _api.warn_deprecated(
        #         version, name=key, obj_type="rcparam", alternative=alt_key
        #     )
        #     return self._get(alt_key) if alt_key else None

        # el

        # In theory, this should only ever be used after the global rcParams
        # has been set up, but better be safe e.g. in presence of breakpoints.
        if key == "backend" and self is globals().get("rcParams"):
            val = self._get(key)
            if val is rcsetup._auto_backend_sentinel:
                from ffmpegio import pyplot as plt

                plt.switch_backend(rcsetup._auto_backend_sentinel)

        return self._get(key)

    def _get_backend_or_none(self):
        """Get the requested backend, if any, without triggering resolution."""
        backend = self._get("backend")
        return None if backend is rcsetup._auto_backend_sentinel else backend

    def __repr__(self):
        class_name = self.__class__.__name__
        indent = len(class_name) + 1
        repr_split = pprint.pformat(dict(self), indent=1, width=80 - indent).split("\n")
        repr_indented = ("\n" + " " * indent).join(repr_split)
        return f"{class_name}({repr_indented})"

    def __str__(self):
        return "\n".join(map("{0[0]}: {0[1]}".format, sorted(self.items())))

    def __iter__(self):
        """Yield sorted list of keys."""
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
    """Construct a `RcParams` instance from the default Matplotlib rc file."""
    return rc_params_from_file(ffmpegio_fname(), fail_on_error)


@contextlib.contextmanager
def _open_file_or_url(fname):

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
    import ffmpegio as mpl

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
            version = "main" if ".post" in mpl.__version__ else f"v{mpl.__version__}"
            _log.warning(
                """
Bad key %(key)s in file %(fname)s, line %(line_no)s (%(line)r)
You probably need to get an updated ffmpegiorc file from
https://github.com/ffmpegio/ffmpegio/blob/%(version)s/lib/ffmpegio/mpl-data/ffmpegiorc
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
        A file with Matplotlib rc settings.
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

    config = RcParams({**rcParamsDefault, **config_from_file})

    _log.debug("loaded rc file %s", fname)

    return config


def _get_data_path(*args):
    """
    Return the `pathlib.Path` to a resource file provided by Matplotlib.

    ``*args`` specify a path relative to the base data path.
    """
    return Path(get_data_path(), *args)


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
dict.update(rcParams, _rc_params_in_file(ffmpegio_fname()))
rcParamsOrig = rcParams.copy()

# This also checks that all rcParams are indeed listed in the template.
# Assigning to rcsetup.defaultParams is left only for backcompat.
defaultParams = rcsetup.defaultParams = {
    # We want to resolve deprecated rcParams, but not backend...
    key: [
        (rcsetup._auto_backend_sentinel if key == "backend" else rcParamsDefault[key]),
        validator,
    ]
    for key, validator in rcsetup._validators.items()
}
if rcParams["axes.formatter.use_locale"]:
    locale.setlocale(locale.LC_ALL, "")


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
        "lw": "linewidth",
        "ls": "linestyle",
        "c": "color",
        "fc": "facecolor",
        "ec": "edgecolor",
        "mew": "markeredgewidth",
        "aa": "antialiased",
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


OPTION_BLACKLIST = {
    "backend",
    "backend_fallback",
    "savefig.directory",
    "docstring.hardcopy",
}


def rcdefaults():
    """
    Restore the `.rcParams` from Matplotlib's internal default style.

    Style-blacklisted `.rcParams` (defined in
    ``ffmpegio.rcparams.OPTION_BLACKLIST``) are not updated.

    See Also
    --------
    ffmpegio.rc_file_defaults
        Restore the `.rcParams` from the rc file originally loaded by
        Matplotlib.
    ffmpegio.style.use
        Use a specific style file.  Call ``style.use('default')`` to restore
        the default style.
    """
    rcParams.clear()
    rcParams.update(
        {k: v for k, v in rcParamsDefault.items() if k not in OPTION_BLACKLIST}
    )


def rc_file_defaults():
    """
    Restore the `.rcParams` from the original rc file loaded by Matplotlib.

    Style-blacklisted `.rcParams` (defined in
    ``ffmpegio.rcparams.OPTION_BLACKLIST``) are not updated.
    """
    rcParams.update(
        {k: rcParamsOrig[k] for k in rcParamsOrig if k not in OPTION_BLACKLIST}
    )


def rc_file(fname, *, use_default_template=True):
    """
    Update `.rcParams` from file.

    Option-blacklisted `.rcParams` (defined in
    ``ffmpegio.rcparams.OPTION_BLACKLIST``) are not updated.

    Parameters
    ----------
    fname : str or path-like
        A file with Matplotlib rc settings.

    use_default_template : bool
        If True, initialize with default parameters before updating with those
        in the given file. If False, the current configuration persists
        and only the parameters specified in the file are updated.
    """
    rc_from_file = rc_params_from_file(fname, use_default_template=use_default_template)
    rcParams.update(
        {k: rc_from_file[k] for k in rc_from_file if k not in OPTION_BLACKLIST}
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
        A file with Matplotlib rc settings. If both *fname* and *rc* are given,
        settings from *rc* take precedence.

    See Also
    --------
    :ref:`customizing-with-ffmpegiorc-files`

    Examples
    --------
    Passing explicit values via a dict::

        with mpl.rc_context({'interactive': False}):
            fig, ax = plt.subplots()
            ax.plot(range(3), range(3))
            fig.savefig('example.png')
            plt.close(fig)

    Loading settings from a file::

         with mpl.rc_context(fname='print.rc'):
             plt.plot(x, y)  # uses 'print.rc'

    Setting in the context body::

        with mpl.rc_context():
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
    [todo] Select the backend used.

    Switch between ffmpeg and pyav backend.

    Parameters
    ----------
    backend : str
        The backend to switch to.  This can either be one of the standard
        backend names, which are case-insensitive:

          ffmpeg, pyav

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
    name = rcsetup.validate_backend(backend)
    # don't (prematurely) resolve the "auto" backend setting
    if rcParams._get_backend_or_none() == name:
        # Nothing to do if the requested backend is already set
        pass
    else:
        raise NotImplementedError("This feature has not been implemented yet")
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


def _replacer(data, value):
    """
    Either returns ``data[value]`` or passes ``data`` back, converts either to
    a sequence.
    """
    try:
        # if key isn't a string don't bother
        if isinstance(value, str):
            # try to use __getitem__
            value = data[value]
    except Exception:
        # key does not exist, silently fall back to key
        pass
    return sanitize_sequence(value)


def _label_from_arg(y, default_name):
    try:
        return y.name
    except AttributeError:
        if isinstance(default_name, str):
            return default_name
    return None


def _add_data_doc(docstring, replace_names):
    """
    Add documentation for a *data* field to the given docstring.

    Parameters
    ----------
    docstring : str
        The input docstring.
    replace_names : list of str or None
        The list of parameter names which arguments should be replaced by
        ``data[name]`` (if ``data[name]`` does not throw an exception).  If
        None, replacement is attempted for all arguments.

    Returns
    -------
    str
        The augmented docstring.
    """
    if docstring is None or replace_names is not None and len(replace_names) == 0:
        return docstring
    docstring = inspect.cleandoc(docstring)

    data_doc = (
        """\
    If given, all parameters also accept a string ``s``, which is
    interpreted as ``data[s]`` (unless this raises an exception)."""
        if replace_names is None
        else f"""\
    If given, the following parameters also accept a string ``s``, which is
    interpreted as ``data[s]`` (unless this raises an exception):

    {', '.join(map('*{}*'.format, replace_names))}"""
    )
    # using string replacement instead of formatting has the advantages
    # 1) simpler indent handling
    # 2) prevent problems with formatting characters '{', '%' in the docstring
    if _log.level <= logging.DEBUG:
        # test_data_parameter_replacement() tests against these log messages
        # make sure to keep message and test in sync
        if "data : indexable object, optional" not in docstring:
            _log.debug("data parameter docstring error: no data parameter")
        if "DATA_PARAMETER_PLACEHOLDER" not in docstring:
            _log.debug("data parameter docstring error: missing placeholder")
    return docstring.replace("    DATA_PARAMETER_PLACEHOLDER", data_doc)


def _preprocess_data(func=None, *, replace_names=None, label_namer=None):
    """
    A decorator to add a 'data' kwarg to a function.

    When applied::

        @_preprocess_data()
        def func(ax, *args, **kwargs): ...

    the signature is modified to ``decorated(ax, *args, data=None, **kwargs)``
    with the following behavior:

    - if called with ``data=None``, forward the other arguments to ``func``;
    - otherwise, *data* must be a mapping; for any argument passed in as a
      string ``name``, replace the argument by ``data[name]`` (if this does not
      throw an exception), then forward the arguments to ``func``.

    In either case, any argument that is a `MappingView` is also converted to a
    list.

    Parameters
    ----------
    replace_names : list of str or None, default: None
        The list of parameter names for which lookup into *data* should be
        attempted. If None, replacement is attempted for all arguments.
    label_namer : str, default: None
        If set e.g. to "namer" (which must be a kwarg in the function's
        signature -- not as ``**kwargs``), if the *namer* argument passed in is
        a (string) key of *data* and no *label* kwarg is passed, then use the
        (string) value of the *namer* as *label*. ::

            @_preprocess_data(label_namer="foo")
            def func(foo, label=None): ...

            func("key", data={"key": value})
            # is equivalent to
            func.__wrapped__(value, label="key")
    """

    if func is None:  # Return the actual decorator.
        return functools.partial(
            _preprocess_data, replace_names=replace_names, label_namer=label_namer
        )

    sig = inspect.signature(func)
    varargs_name = None
    varkwargs_name = None
    arg_names = []
    params = list(sig.parameters.values())
    for p in params:
        if p.kind is Parameter.VAR_POSITIONAL:
            varargs_name = p.name
        elif p.kind is Parameter.VAR_KEYWORD:
            varkwargs_name = p.name
        else:
            arg_names.append(p.name)
    data_param = Parameter("data", Parameter.KEYWORD_ONLY, default=None)
    if varkwargs_name:
        params.insert(-1, data_param)
    else:
        params.append(data_param)
    new_sig = sig.replace(parameters=params)
    arg_names = arg_names[1:]  # remove the first "ax" / self arg

    assert {*arg_names}.issuperset(replace_names or []) or varkwargs_name, (
        "Matplotlib internal error: invalid replace_names "
        f"({replace_names!r}) for {func.__name__!r}"
    )
    assert label_namer is None or label_namer in arg_names, (
        "Matplotlib internal error: invalid label_namer "
        f"({label_namer!r}) for {func.__name__!r}"
    )

    @functools.wraps(func)
    def inner(ax, *args, data=None, **kwargs):
        if data is None:
            return func(ax, *map(sanitize_sequence, args), **kwargs)

        bound = new_sig.bind(ax, *args, **kwargs)
        auto_label = bound.arguments.get(label_namer) or bound.kwargs.get(label_namer)

        for k, v in bound.arguments.items():
            if k == varkwargs_name:
                for k1, v1 in v.items():
                    if replace_names is None or k1 in replace_names:
                        v[k1] = _replacer(data, v1)
            elif k == varargs_name:
                if replace_names is None:
                    bound.arguments[k] = tuple(_replacer(data, v1) for v1 in v)
            else:
                if replace_names is None or k in replace_names:
                    bound.arguments[k] = _replacer(data, v)

        new_args = bound.args
        new_kwargs = bound.kwargs

        args_and_kwargs = {**bound.arguments, **bound.kwargs}
        if label_namer and "label" not in args_and_kwargs:
            new_kwargs["label"] = _label_from_arg(
                args_and_kwargs.get(label_namer), auto_label
            )

        return func(*new_args, **new_kwargs)

    inner.__doc__ = _add_data_doc(inner.__doc__, replace_names)
    inner.__signature__ = new_sig
    return inner

_backend_mod = None

def switch_backend(newbackend: str) -> None:
    """
    Set the ffmpegio backend between ffmpeg subprocess vs. pyav.

    Parameters
    ----------
    newbackend : str
        The case-insensitive name of the backend to use.

    """

    if newbackend is rcsetup._auto_backend_sentinel:
        mapping = {'ffmpeg': 'ffmpegprocess'}

        candidates += [
            "macosx", "qtagg", "gtk4agg", "gtk3agg", "tkagg", "wxagg"]

        # Don't try to fallback on the cairo-based backends as they each have
        # an additional dependency (pycairo) over the agg-based backend, and
        # are of worse quality.
        for candidate in candidates:
            try:
                switch_backend(candidate)
            except ImportError:
                continue
            else:
                rcParamsOrig['backend'] = candidate
                return
        else:
            # Switching to Agg should always succeed; if it doesn't, let the
            # exception propagate out.
            switch_backend("agg")
            rcParamsOrig["backend"] = "agg"
            return
    # have to escape the switch on access logic
    old_backend = dict.__getitem__(rcParams, 'backend')

    module = importlib.import_module(cbook._backend_module_name(newbackend))

    # Classically, backends can directly export these functions.  This should
    # keep working for backcompat.
    new_figure_manager = getattr(module, "new_figure_manager", None)
    show = getattr(module, "show", None)

    # In that classical approach, backends are implemented as modules, but
    # "inherit" default method implementations from backend_bases._Backend.
    # This is achieved by creating a "class" that inherits from
    # backend_bases._Backend and whose body is filled with the module globals.
    class backend_mod(matplotlib.backend_bases._Backend):
        locals().update(vars(module))

    # We can't compare directly manager_class.pyplot_show and FMB.pyplot_show because
    # pyplot_show is a classmethod so the above constructs are bound classmethods, and
    # thus always different (being bound to different classes).  We also have to use
    # getattr_static instead of vars as manager_class could have no __dict__.
    manager_pyplot_show = inspect.getattr_static(manager_class, "pyplot_show", None)
    base_pyplot_show = inspect.getattr_static(FigureManagerBase, "pyplot_show", None)
    if (show is None
            or (manager_pyplot_show is not None
                and manager_pyplot_show != base_pyplot_show)):
        if not manager_pyplot_show:
            raise ValueError(
                f"Backend {newbackend} defines neither FigureCanvas.manager_class nor "
                f"a toplevel show function")
        _pyplot_show = cast('Any', manager_class).pyplot_show
        backend_mod.show = _pyplot_show  # type: ignore[method-assign]

    _log.debug("Loaded backend %s version %s.",
               newbackend, backend_mod.backend_version)

    rcParams['backend'] = rcParamsDefault['backend'] = newbackend
    _backend_mod = backend_mod
    for func_name in ["new_figure_manager", "draw_if_interactive", "show"]:
        globals()[func_name].__signature__ = inspect.signature(
            getattr(backend_mod, func_name))

    # Need to keep a global reference to the backend for compatibility reasons.
    # See https://github.com/matplotlib/matplotlib/issues/6092
    matplotlib.backends.backend = newbackend  # type: ignore[attr-defined]

    if not cbook._str_equal(old_backend, newbackend):
        if get_fignums():
            _api.warn_deprecated("3.8", message=(
                "Auto-close()ing of figures upon backend switching is deprecated since "
                "%(since)s and will be removed %(removal)s.  To suppress this warning, "
                "explicitly call plt.close('all') first."))
        close("all")

    # Make sure the repl display hook is installed in case we become interactive.
    install_repl_displayhook()

_log.debug("platform is %s", sys.platform)


