import pytest

from ffmpegio.plugins import pm, rawdata_bytes

# test only with the base plugins
@pytest.fixture(scope="session", autouse=True)
def no_extra_plugins():
    base_plugins = (rawdata_bytes,)
    plugins = [p for p in pm.get_plugins() if p not in base_plugins]
    for p in plugins:
        pm.unregister(p)
    yield
    for p in reversed(plugins):
        pm.register(p)
