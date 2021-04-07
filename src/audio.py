import numpy as np
import ffmpeg

def read(filename,**opts):
    return 44100, np.zeros(0)

def write(filename, rate, data):
    pass