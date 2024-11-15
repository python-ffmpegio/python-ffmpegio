from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

from typing import Literal, Any

from importlib import import_module
import re, os
import pluggy


from . import hookspecs

__all__ = ["initialize", "get_hook"]

pm = pluggy.PluginManager("ffmpegio")
pm.add_hookspecs(hookspecs)


def _try_register_builtin(plugin_name: str, reregister: bool = False) -> str | None:
    module_package, module_name = plugin_name.rsplit(".", 1)
    try:
        module = import_module(f".{module_name}", module_package)
    except ModuleNotFoundError:
        logger.info(
            f"Skip importing {module_name} builtin-plugin module, likely missing dependency"
        )
    else:
        registered = pm.has_plugin(plugin_name)
        if not reregister and registered:
            return
        if registered:
            pm.unregister(module)
        name = pm.register(module)
        logger.info(f"registered {name} builtin-plugin module")
        return name


def register(plugin: object, name: str | None = None) -> str | None:
    """Register a plugin and return its name.

    :param plugin: Plugin object
    :param name: The name under which to register the plugin. If not specified,
                 a name is generated using get_canonical_name().
    :returns: The plugin name. If the name is blocked from registering, returns None.

    If the plugin is already registered, raises a ValueError.
    """
    return pm.register(plugin, name)


def unregister(name: str) -> Any | None:
    """Register a plugin and return its name.

    :param name: The name of the plugin to unregister .
    :returns: The plugin name. If the name is blocked from registering, returns None.

    If the plugin is already registered, raises a ValueError.
    """
    return pm.unregister(name)

def list_plugins() -> list:
    return [pm.get_name(p) for p in pm.get_plugins()]

def use(name: Literal["read_numpy", "read_bytes"] | str):
    """Select the plugin to use (among contentious plugins)

    :param name: The plugin to use. This can either be ``'read_numpy'`` or
                 ``'read_bytes'`` or a plugin module name:

                 - ``"read_numpy"`` - All the media readers to output a Numpy array.
                               Also, reverts Numpy array input processing by
                               all the writers to the default. Numpy must be
                               installed for this plugin to be activated.
                 - ``"read_bytes"`` - All the media readers to output a dict with keys:
                                    ``"buffer"`` (``bytes``) of the retrieved data,
                                    ``"dtype"`` (``str``) Numpy dtype string of ``'"buffer"'``,
                                    and ``"shape"`` (``tuple`` of ``int``s) the data array shape
                                    of ``'"buffer"'``

                 If a plugin name is given, it must be in the form:
                 `plugin://my.plugin.name`.
    """

    if name == "read_numpy":
        _try_register_builtin("ffmpegio.plugins.rawdata_numpy", True)
    elif name == "read_bytes":
        _try_register_builtin("ffmpegio.plugins.rawdata_bytes", True)
    else:
        matched_name = re.match(r"plugin://(.+)$", name)
        if matched_name is None:
            raise ValueError(f'{name=} must follow "plugin://my.plugin.name" format')
        plugin = pm.get_plugin(matched_name)
        if plugin is None:
            raise ValueError(f"Requested plugin ({name=}) has not been registered")
        pm.unregister(plugin)
        pm.register(plugin)


def initialize():
    """initilaize manager and load builtin plugins"""

    _try_register_builtin("ffmpegio.plugins.finder_syspath")

    if os.name == "nt":
        for name in ["finder_win32"]:
            _try_register_builtin(f"ffmpegio.plugins.{name}")

        from .devices import dshow

        pm.register(dshow)

    for name in ["rawdata_bytes", "finder_ffdl", "rawdata_mpl", "rawdata_numpy"]:
        _try_register_builtin(f"ffmpegio.plugins.{name}")

    # load all ffmpegio plugins found in site-packages
    pm.load_setuptools_entrypoints("ffmpegio")


def get_hook():
    return pm.hook
