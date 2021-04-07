#!/usr/bin/python
# -*- coding: utf-8 -*-

import numpy as np
import json
import ffmpeg
import shutil
import logging
import sys
import os
import re
import subprocess as sp
from . import caps

# add FFmpeg directory to the system path as given in system environment variable FFMPEG_DIR
FFMPEG_DIR = ""


def get_ffmpeg_dir():
    return FFMPEG_DIR


def set_ffmpeg_dir(dir=""):
    """utility function to add FFmpeg bin directory to system path"""

    global FFMPEG_DIR

    if dir:
        p = os.environ["PATH"]
        if FFMPEG_DIR:
            p.replace(FFMPEG_DIR, dir, 1)
        elif p.find(dir) < 0:
            p = dir + os.pathsep + p  # prepend
        os.environ["PATH"] = p
        FFMPEG_DIR = dir

    # check if ffmpeg and ffprobe are accessible
    return shutil.which("ffmpeg") and shutil.which("ffprobe")


def get_format_info(inputFileName):
    """get media container info of the media file

    inputFileName (str): media file path
    """
    return ffmpeg.probe(inputFileName).get("format", dict())










