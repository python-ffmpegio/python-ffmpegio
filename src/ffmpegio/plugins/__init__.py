import pluggy

from . import hookspecs, rawdata_bytes


pm = pluggy.PluginManager("ffmpegio")
pm.add_hookspecs(hookspecs)

# load bundled base plugins
pm.register(rawdata_bytes)

# load all ffmpegio plugins found in site-packages
pm.load_setuptools_entrypoints("ffmpegio")

def get_hook():
    return pm.hook
