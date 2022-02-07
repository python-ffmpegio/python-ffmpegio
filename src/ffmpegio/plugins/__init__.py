import pluggy

from . import hookspecs, rawdata_bytes


pm = pluggy.PluginManager("ffmpegio")
pm.add_hookspecs(hookspecs)
pm.load_setuptools_entrypoints("ffmpegio")
pm.register(rawdata_bytes)


def get_hook():
    return pm.hook
