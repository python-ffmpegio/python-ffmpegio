import numpy as np
import ffmpeg

def read(filename,format=None,**options):
    return np.zeros((100,100))

def write(A, filename, map=None, format=None, **options):
    pass

# https://ffmpeg.org/ffmpeg-codecs.html
# 9.2 GIF
# GIF image/animation encoder.
# 9.4 jpeg2000
# The native jpeg 2000 encoder is lossy by default, the -q:v option can be used 
# to set the encoding quality. Lossless encoding can be selected with -pred 1.
# 9.19 png
# PNG image encoder.
