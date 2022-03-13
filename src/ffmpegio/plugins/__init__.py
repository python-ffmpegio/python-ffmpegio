import pluggy, os

from . import hookspecs

__all__ = ["initialize", "get_hook"]

pm = pluggy.PluginManager("ffmpegio")
pm.add_hookspecs(hookspecs)


def initialize():
    from . import rawdata_bytes

    # load bundled base plugins
    pm.register(rawdata_bytes)
    if os.name == "nt":
        from . import finder_win32
        pm.register(finder_win32)

        from .devices import dshow
        pm.register(dshow)

    # load all ffmpegio plugins found in site-packages
    pm.load_setuptools_entrypoints("ffmpegio")


def get_hook():
    return pm.hook
