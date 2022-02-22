import pluggy, os

from . import hookspecs, rawdata_bytes, finder_win32

__all__ = ["get_hook"]

pm = pluggy.PluginManager("ffmpegio")
pm.add_hookspecs(hookspecs)

# load bundled base plugins
pm.register(rawdata_bytes)
if os.name=='nt':
    pm.register(finder_win32)

# load all ffmpegio plugins found in site-packages
pm.load_setuptools_entrypoints("ffmpegio")


def get_hook():
    return pm.hook
