import pytest

from ffmpegio.plugins import pm, rawdata_bytes, finder_win32

# test only with the base plugins
@pytest.fixture(scope="session", autouse=True)
def no_extra_plugins():
    base_plugins = (rawdata_bytes, finder_win32)
    plugins = [p for p in pm.get_plugins() if p not in base_plugins and pm.get_name(p)!='finder_downloader']
    for p in plugins:
        pm.unregister(p)
    yield
    for p in reversed(plugins):
        pm.register(p)
