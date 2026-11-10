import logging
import os
from ffmpegio.plugins.devices import dshow
from ffmpegio.path import check_version
from ffmpegio import devices
import pytest


@pytest.mark.skipif(os.name != "nt", reason="only run on windows")
def test_dshow():
    if check_version("5.0"):
        devices.scan()
        try:
            devs = devices.SOURCES["dshow"]["list"]
        except:
            print("no dshow device found")
            return
    else:
        devs = dshow._scan()
    for _, spec in devs.items():
        print(dshow._resolve([spec]))
        print(dshow._list_options(spec))
    if devs:
        print(dshow._resolve([dev for dev in devs.values()]))
