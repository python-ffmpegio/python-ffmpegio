"""
The rcsetup module contains the validation code for customization using
ffmpegio's rc settings.

Each rc setting is assigned a function used to validate any attempted changes
to that setting.  The validation functions are defined in the rcsetup module,
and are used to construct the rcParams global object which stores the settings
and is referenced throughout ffmpegio.

The default values of the rc settings are set in the default matplotlibrc file.
Any additions or deletions to the parameter set listed here should also be
propagated to the :file:`lib/matplotlib/mpl-data/matplotlibrc` in ffmpegio's
root source directory.
"""

import ast
from functools import lru_cache, reduce, partial
from numbers import Real
import operator
import os
import re

import numpy as np

from matplotlib import _api, cbook
from matplotlib.cbook import ls_mapper
from matplotlib.colors import Colormap, is_color_like
from matplotlib._fontconfig_pattern import parse_fontconfig_pattern
from matplotlib._enums import JoinStyle, CapStyle

# Don't let the original cycler collide with our validating cycler
from cycler import Cycler, cycler as ccycler


class _ignorecase(list):
    """A marker class indicating that a list-of-str is case-insensitive."""


def _convert_validator_spec(key, conv):
    if isinstance(conv, list):
        ignorecase = isinstance(conv, _ignorecase)
        return ValidateInStrings(key, conv, ignorecase=ignorecase)
    else:
        return conv


class ValidateInStrings:
    def __init__(self, key, valid, ignorecase=False, *, _deprecated_since=None):
        """*valid* is a list of legal strings."""
        self.key = key
        self.ignorecase = ignorecase
        self._deprecated_since = _deprecated_since

        def func(s):
            if ignorecase:
                return s.lower()
            else:
                return s

        self.valid = {func(k): k for k in valid}

    def __call__(self, s):
        if self._deprecated_since:
            (name,) = (k for k, v in globals().items() if v is self)
            _api.warn_deprecated(self._deprecated_since, name=name, obj_type="function")
        if self.ignorecase and isinstance(s, str):
            s = s.lower()
        if s in self.valid:
            return self.valid[s]
        msg = (
            f"{s!r} is not a valid value for {self.key}; supported values "
            f"are {[*self.valid.values()]}"
        )
        if (
            isinstance(s, str)
            and (
                s.startswith('"')
                and s.endswith('"')
                or s.startswith("'")
                and s.endswith("'")
            )
            and s[1:-1] in self.valid
        ):
            msg += "; remove quotes surrounding your string"
        raise ValueError(msg)


@lru_cache
def _listify_validator(scalar_validator, allow_stringlist=False, *, n=None, doc=None):
    def f(s):
        if isinstance(s, str):
            try:
                val = [scalar_validator(v.strip()) for v in s.split(",") if v.strip()]
            except Exception:
                if allow_stringlist:
                    # Sometimes, a list of colors might be a single string
                    # of single-letter colornames. So give that a shot.
                    val = [scalar_validator(v.strip()) for v in s if v.strip()]
                else:
                    raise
        # Allow any ordered sequence type -- generators, np.ndarray, pd.Series
        # -- but not sets, whose iteration order is non-deterministic.
        elif np.iterable(s) and not isinstance(s, (set, frozenset)):
            # The condition on this list comprehension will preserve the
            # behavior of filtering out any empty strings (behavior was
            # from the original validate_stringlist()), while allowing
            # any non-string/text scalar values such as numbers and arrays.
            val = [scalar_validator(v) for v in s if not isinstance(v, str) or v]
        else:
            raise ValueError(f"Expected str or other non-set iterable, but got {s}")
        if n is not None and len(val) != n:
            raise ValueError(
                f"Expected {n} values, but there are {len(val)} values in {s}"
            )
        return val

    try:
        f.__name__ = f"{scalar_validator.__name__}list"
    except AttributeError:  # class instance.
        f.__name__ = f"{type(scalar_validator).__name__}List"
    f.__qualname__ = f.__qualname__.rsplit(".", 1)[0] + "." + f.__name__
    f.__doc__ = doc if doc is not None else scalar_validator.__doc__
    return f


def validate_any(s):
    return s


validate_anylist = _listify_validator(validate_any)


def _validate_date(s):
    try:
        np.datetime64(s)
        return s
    except ValueError:
        raise ValueError(
            f"{s!r} should be a string that can be parsed by numpy.datetime64"
        )


def validate_bool(b):
    """Convert b to ``bool`` or raise."""
    if isinstance(b, str):
        b = b.lower()
    if b in ("t", "y", "yes", "on", "true", "1", 1, True):
        return True
    elif b in ("f", "n", "no", "off", "false", "0", 0, False):
        return False
    else:
        raise ValueError(f"Cannot convert {b!r} to bool")


def _make_type_validator(cls, *, allow_none=False):
    """
    Return a validator that converts inputs to *cls* or raises (and possibly
    allows ``None`` as well).
    """

    def validator(s):
        if allow_none and (s is None or isinstance(s, str) and s.lower() == "none"):
            return None
        if cls is str and not isinstance(s, str):
            raise ValueError(f"Could not convert {s!r} to str")
        try:
            return cls(s)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Could not convert {s!r} to {cls.__name__}") from e

    validator.__name__ = f"validate_{cls.__name__}"
    if allow_none:
        validator.__name__ += "_or_None"
    validator.__qualname__ = (
        validator.__qualname__.rsplit(".", 1)[0] + "." + validator.__name__
    )
    return validator


validate_string = _make_type_validator(str)
validate_string_or_None = _make_type_validator(str, allow_none=True)
validate_stringlist = _listify_validator(
    validate_string, doc="return a list of strings"
)
validate_int = _make_type_validator(int)
validate_int_or_None = _make_type_validator(int, allow_none=True)
validate_float = _make_type_validator(float)
validate_float_or_None = _make_type_validator(float, allow_none=True)
validate_floatlist = _listify_validator(validate_float, doc="return a list of floats")


def _validate_pathlike(s, isdir=False, check_exists=True):

    if not isinstance(s, (str, os.PathLike)):
        s = validate_string(s)
    s = os.fsdecode(s)

    if check_exists and not os.path.exists(s):
        raise ValueError(f"Could not find {s} in the file system")

    return s


_reader_format_shortnames = {
    "bytes": "ffmpegio.plugins.rawdata_bytes",
    "numpy": "rawdata_numpy",
}


def _validate_reader_formatter(s, mediatype=None):

    from . import plugins

    # must specify a module containing `bytes_to_video` and `bytes_to_audio`
    name = _reader_format_shortnames.get(s, s)
    name = validate_string_or_None(name)

    pin = plugins.pm.get_plugin(name)
    callers = [hc.name for hc in plugins.pm.get_hookcallers(pin)]

    for t in ("audio", "video") if mediatype is None else [mediatype]:
        name = f"bytes_to_{t}"
        if name not in callers:
            raise ValueError(f"Plugin module {s} does not support {name} hook")

    return name


def _validate_int_greaterequal0(s):
    s = validate_int(s)
    if s >= 0:
        return s
    else:
        raise RuntimeError(f"Value must be >=0; got {s}")

def _validate_opt_dict(s):
    

class _ignorecase(list):
    """A marker class indicating that a list-of-str is case-insensitive."""


def _convert_validator_spec(key, conv):
    if isinstance(conv, list):
        ignorecase = isinstance(conv, _ignorecase)
        return ValidateInStrings(key, conv, ignorecase=ignorecase)
    else:
        return conv


# Mapping of rcParams to validators.
# Converters given as lists or _ignorecase are converted to ValidateInStrings
# immediately below.
# The rcParams defaults are defined in lib/matplotlib/mpl-data/matplotlibrc, which
# gets copied to matplotlib/mpl-data/matplotlibrc by the setup script.
_validators = {
    "path.ffmpeg": _validate_pathlike,
    "path.ffprobe": _validate_pathlike,
    "reader.formatter.default": _validate_reader_formatter,
    "reader.formatter.audio": partial(_validate_reader_formatter, mediatype="audio"),
    "reader.formatter.video": partial(_validate_reader_formatter, mediatype="video"),
    "reader.formatter.image": partial(_validate_reader_formatter, mediatype="video"),
    "subprocess.default_kwargs": ...,
    "ffmpeg.default_global_kwargs": ...,
    "ffmpeg.default_input_kwargs": ...,
    "ffmpeg.default_output_kwargs": ...,
    "ffprobe.default_kwargs": ...,
    # "backend": validate_backend (ffmpeg|pyav),
    # "backend_fallback": validate_bool,
}
_hardcoded_defaults = {  # Defaults not inferred from
    # lib/matplotlib/mpl-data/matplotlibrc...
    # ... because they are private:
    # ... because they are deprecated:
    # No current deprecations.
    # backend is handled separately when constructing rcParamsDefault.
}
_validators = {k: _convert_validator_spec(k, conv) for k, conv in _validators.items()}
