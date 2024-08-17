from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

import pluggy, os

from importlib import import_module

from . import hookspecs

__all__ = ["initialize", "get_hook"]

pm = pluggy.PluginManager("ffmpegio")
pm.add_hookspecs(hookspecs)


def _try_register_builtin(module_name: str) -> str | None:
    try:
        module = import_module(f".{module_name}", "ffmpegio.plugins")
    except:
        logger.info(
            f"Skip importing {module_name} builtin-plugin module, likely missing dependency"
        )
    else:
        logger.info(f"registered {module_name} builtin-plugin module")
        return pm.register(module)


def initialize():
    from . import rawdata_bytes

    # load bundled base plugins
    pm.register(rawdata_bytes)
    if os.name == "nt":
        for name in ["finder_win32"]:
            _try_register_builtin(name)

        from .devices import dshow

        pm.register(dshow)

    for name in ["finder_ffdl", "mpl_writer", "numpy_data"]:
        _try_register_builtin(name)

    # load all ffmpegio plugins found in site-packages
    pm.load_setuptools_entrypoints("ffmpegio")


def get_hook():
    return pm.hook
