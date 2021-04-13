import ffmpegio
import tempfile, re
from os import path
import numpy as np
from matplotlib import pyplot as plt

# url = "tests/assets/testvideo-5m.mpg"
url = "tests/assets/testvideo-43.avi"
# url = "tests/assets/testvideo-169.avi"

with ffmpegio.open(url, "rv") as f:
    F = f.read(5)
    print(F.shape)
