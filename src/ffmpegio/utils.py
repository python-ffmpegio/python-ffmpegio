import sys, logging
import ffmpeg

def _ffmpeg_output(inputFileName, inopts, outopts, filters):
    try:
        stream = ffmpeg.input(inputFileName, **inopts)
        for filter in filters:
            stream = (
                stream.filter(*(filter[:-1]), **filter[-1])
                if type(filter[-1]) == dict
                else stream.filter(*filter)
            )
        return stream.output("pipe:", **outopts)
    except ffmpeg.Error as e:
        logging.critical(e.stderr.decode(), file=sys.stderr)
        sys.exit(1)

def _ffmpeg_input(outputFileName, inopts, outopts, filters):
    try:
        stream = ffmpeg.input("pipe:", **inopts)
        for filter in filters:
            stream = (
                stream.filter(*(filter[:-1]), **filter[-1])
                if type(filter[-1]) == dict
                else stream.filter(*filter)
            )
        return stream.output(outputFileName, **outopts)
    except ffmpeg.Error as e:
        logging.critical(e.stderr.decode(), file=sys.stderr)
        sys.exit(1)

def _ffmpeg_transcode(inputFileName, outputFileName, inopts, outopts, filters):
    try:
        stream = ffmpeg.input(inputFileName, **inopts)
        for filter in filters:
            stream = (
                stream.filter(*(filter[:-1]), **filter[-1])
                if type(filter[-1]) == dict
                else stream.filter(*filter)
            )
        return stream.output(outputFileName, **outopts)
    except ffmpeg.Error as e:
        logging.critical(e.stderr.decode(), file=sys.stderr)
        sys.exit(1)
