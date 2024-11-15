import pytest

import ffmpegio as ff


# test only with the base plugins
@pytest.fixture(scope="session", autouse=True)
def no_extra_plugins():
    ff.use("read_bytes")
    # base_plugins = (rawdata_bytes, finder_win32, finder_ffdl)
    # plugins = [p for p in pm.get_plugins() if p not in base_plugins]
    # for p in plugins:
    #     pm.unregister(p)
    # yield
    # for p in reversed(plugins):
    #     pm.register(p)
