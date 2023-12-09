import re
from typing import Sequence, Union


class FFmpegioError(Exception):
    pass


ERROR_MESSAGES = (
    # cmdutils.c::parse_optgroup()
    r"Option %s (%s) cannot be applied to %s %s",
    # cmdutils.c::opt_default()
    r"Directly using swscale dimensions/format options is not supported, please use the -s or -pix_fmt options",
    r"Error setting option .+?\.",
    # cmdutils.c::split_commandline()
    r"Missing argument for option '.+?'\.",
    r"Error parsing option '.+?' with argument '.+?'\.",
    r"Unrecognized option '.+?'\.",
    # cmdutils.c::check_stream_specifier()
    r"Invalid stream specifier: .+?\.",
    # ffmpeg_filter.c::insert_trim()
    r".+? filter not present, cannot limit recording time.",
    r"Error configuring the .+? filter",
    # ffmpeg_filter.c::configure_input_video_filter()
    r"Cannot connect video filter to audio input",
    # ffmpeg_filter.c::configure_input_audio_filter()
    r"Cannot connect audio filter to non audio input",
    # ffmpeg_filter.c::configure_input_filter()
    r"No decoder for stream #\d+:\d+, filtering impossible"
    # ffmpeg_filter.c::configure_filtergraph()
    r"Encoder \(codec .+?\) not found for output stream #d+:\d+",
    # ffmpeg_hw.c::hw_device_init_from_string()
    r"Invalid device specification ",
    r"Device creation failed: \d+\.",
    # ffmpeg_hw.c::hwaccel_retrieve_data()
    r"Failed to transfer data to output frame: ",
    # ffmpeg_opt.c::opt_filter_hw_device()
    r"Only one filter device can be used",
    r"Invalid filter device ",
    # ffmpeg_opt.c::new_audio_stream()
    r"Cannot determine input stream for channel mapping ",
    # ffmpeg_opt.c::open_output_file()
    r".+?: Cannot allocate memory",  # ...
    # ffmpeg_opt.c::opt_target()
    r"Unknown target: ",
    # ffmpeg_opt.c::open_files()
    r"Error parsing options for .+? file ",  # -1
    r"Error opening .+ file ",  # -1
    # ffmpeg.c::process_input_packet()
    r"Error while decoding stream ",
    r".+? hwaccel requested for input stream #\d+:d+, but cannot be initialized",
)

FINAL_ERROR_MESSAGES = (
    # cmdutils.c::parse_number_or_die()
    r"Expected number for .+? but found: ",
    r"The value for .+? was .+? which is not within ",
    r"Expected int64 for .+? but found ",
    r"Expected int for .+? but found ",
    # ffmpeg_filter.c::init_input_filter()
    r"Only video and audio filters supported currently",
    r"Invalid file index \d+ in filtergraph description ",
    r"Stream specifier '.+?' in filtergraph description .+? matches a disabled input stream",
    r"Cannot find a matching stream for unlabeled input pad \d+ on filter ",
    # ffmpeg_opt.c::opt_map_channel()
    r"mapchan: invalid input file index: ",
    r"mapchan: invalid input file stream index ",
    r"mapchan: invalid audio channel #\d+.\d+.\d+"  # +1
    # ffmpeg_opt.c::parse_meta_type()
    r"Invalid metadata specifier ",
    r"Invalid metadata type ",
    # ffmpeg_opt.c::copy_metadata()
    r"Invalid .+? index \d+ while processing metadata maps",
    r"Stream specifier .+? does not match  any streams",
    # ffmpeg_opt.c::find_codec_or_die()
    r"Unknown .+? '.+?'",
    r"Invalid .+? type '.+?'",
    # ffmpeg_opt.c::add_input_streams()
    r"Error parsing discard ",
    r"Error allocating the decoder context",
    r"Error initializing the decoder context",
    r"Error parsing framerate ",
    r"Invalid canvas size: ",
    r"Error initializing the decoder context",
    # ffmpeg_opt.c::dump_attachment()
    r"No filename specified and no 'filename' tag in stream #\d+:\d+",
    r"Could not open file .+? for writing",
    # ffmpeg_opt.c::open_input_file()
    r"-to value smaller than -ss; aborting",
    r"Unknown input format: ",
    r".+?: Cannot allocate memory",  # ...
    r": could not find codec parameters",
    r"-sseof value must be negative; aborting",
    r"Option -readrate for Input #\d+ is .+?; it must be non-negative",
    r"Codec AVOption .+? \(.+?\) specified for input file #\d+ \(.+?\) is not a decoding option",
    # ffmpeg_opt.c::get_line()
    r"Could not alloc buffer for reading preset",
    # ffmpeg_opt.c::new_output_stream()
    r"Could not alloc stream",
    r"Error allocating the encoding context",
    r"Error allocating the encoding parameters",
    r"Invalid line found in the preset file",
    r"Preset .+? specified for stream \d+:\d+, but could not be opened",
    r"Invalid time base: ",
    r"Error parsing bitstream filter sequence ",
    # ffmpeg_opt.c::parse_matrix_coeffs()
    r"Syntax error in matrix \".+?\" at coeff \d+",
    # ffmpeg_opt.c::get_ost_filters()
    r"Both -filter and -filter_script set for output stream ",
    # ffmpeg_opt.c::new_video_stream()
    r"Invalid framerate value: ",
    r"Invalid maximum framerate value: ",
    r"Only one of -fpsmax and -r can be set for a stream",
    r"Invalid aspect ratio: ",
    r"Invalid frame size: ",
    r"Unknown pixel format requested: ",
    r"Could not allocate memory for intra matrix",
    r"Could not allocate memory for inter matrix",
    r"error parsing rc_override",
    r"Could not (re)allocate memory for rc_override",
    r"Error reading log file '.+?' for pass-2 encoding",
    r"Cannot write log file '.+?' for pass-1 encoding: ",
    # ffmpeg_opt.c::new_audio_stream()
    r"Invalid sample format ",
    # ffmpeg_opt.c::new_data_stream()
    r"Data stream encoding not supported yet \(only streamcopy\)",
    # ffmpeg_opt.c::new_unknown_stream()
    r"Unknown stream encoding not supported yet \(only streamcopy\)",
    # ffmpeg_opt.c::new_subtitle_stream()
    r"Invalid frame size: ",
    # ffmpeg_opt.c::opt_streamid()
    r"Invalid value '.+?' for option '.+?', required syntax is 'index:value'",
    # ffmpeg_opt.c::init_output_filter()
    r"Only video and audio filters are supported currently",
    r"Filtergraph( script?) '.+?' was specified through the .+? option for output stream \d+:\d+, which is fed from a complex filtergraph",  # +1
    # ffmpeg_opt.c::open_output_file()
    r"-to value smaller than -ss; aborting.",
    r"Output with label '.+?' does not exist in any defined filter graph, or was already used elsewhere"
    r"Stream #\d+:\d+ is disabled and cannot be mapped",
    r"Cannot map stream #\d+:\d+ - unsupported type",  # +2, [next line] 'If you want them copied, please use -copy_unknown'
    r"Could not open attachment file ",
    r"Could not get size of the attachment ",
    r"Attachment .+? too large",
    r"Output file #\d+ does not contain any stream",
    r"Codec AVOption .+? \(.+?\) specified for output file #\d+ \(.+?\) is not an encoding option",
    r"Error initializing a simple filtergraph between streams ",
    r"No input streams but output needs an input stream",
    r"Invalid input file index \d+ while processing metadata maps",
    r"Invalid input file index \d+ in chapter mapping",
    r"No '=' character in program string ",
    r"Unknown program key ",
    r"No '=' character in metadata string ",
    r"Invalid chapter index \d+ in metadata specifier",
    r"Invalid program index \d+ in metadata specifier",
    r"Invalid metadata specifier ",
    r"Error setting output stream dispositions",
    # ffmpeg_opt::opt_vstats()
    r"Unable to get current time: ",
    # ffmpeg_opt.c::opt_preset()
    r"Please use -preset <speed> -qp 0",
    r"File for preset '.+?' not found",
    r".+?: Invalid syntax: ",
    r".+?: Invalid option or argument: ",
    # ffmpeg.c::assert_avoptions()
    r"Option .+? not found",
    # ffmpeg.c::write_packet()
    r"Too many packets buffered for output stream ",
    r"Non-monotonous DTS in output stream ",
    # ffmpeg.c::output_packet()
    r"Error applying bitstream filters to an output packet for stream",
    # ffmpeg.c::do_audio_out()
    r"Audio encoding failed",
    # ffmpeg.c::do_video_out()
    r"Subtitle packets must have a pts",
    r"Failed to allocate subtitle_out",
    r"Subtitle encoding failed",
    r"Video encoding failed",
    # ffmpeg.c::flush_encoders()
    r"Error configuring filter graph",
    r".+? encoding failed: ",
    # ffmpeg.c::check_decode_result()
    r".+?: corrupt decoded frame in stream ",
    # ffmpeg.c::process_input_packet()
    r"Error marking filters as finished",
    # ffmpeg.c::init_output_stream_streamcopy()
    r"-acodec copy and -vol are incompatible \(frames are not decoded\)"
    # ffmpeg.c::parse_forced_key_frames()
    r"Could not allocate forced key frames array",
    r"Error initializing the output stream codec context",
    # ffmpeg.c::process_input()
    r".+?: corrupt input packet in stream \d+",
    # ffmpeg.c::transcode()
    r"Error writing trailer of ",
    r"Error closing file ",
    r"Empty output on stream ",
    r"Empty output",
)

# endswith("aborting.")


def scan_stderr(logs: Union[str, Sequence[str], None]):
    msg = ""

    if logs is None:
        return msg

    if isinstance(logs, str):
        logs = re.split(r"[\n\r]+", logs.rstrip())

    if logs[0].startswith("Unknown help option "):
        msg = logs[0]
    else:
        msg0 = logs[-1]
        if msg0 == '"trace"':
            msg = "\n  ".join(logs)
        elif msg0 == "Use -h to get full help or, even better, run 'man ffmpeg'":
            msg = "No ffmpeg command argument specified"
        elif msg0 == "Invalid argument":  # generic
            msg = logs[-2]
            if msg == "Error initializing complex filters.":
                msg = f"{logs[-3]}\n  {msg}"
        elif msg0 == "To ignore this, add a trailing '?' to the map.":
            msg = f"{logs[-2]}\n  {msg0}"
        elif msg0 == "Filtering and streamcopy cannot be used together.":
            msg = f"{logs[-2]}\n  {msg0}"
        elif msg0 == "FFmpeg cannot edit existing files in-place.":
            msg = f"{logs[-2]}\n  {msg0}"
        elif msg0 == 'or set a framerate with "-r xxx".':
            msg = "\n  ".join(logs[-3:])
        elif msg0.startswith("Error opening input files"):
            err = logs[-2]
            i = -2
            msg = "\n  ".join(logs[i:])
        elif msg0.startswith(
            "Error opening output file"
        ):  # <v6.1, "Error opening output files: "
            err = logs[-2]
            i = -2
            if err.startswith("Error parsing options for output file "):
                m = re.match(r"Failed to set value '.+?' for option '(.+?)':", logs[-3])
                if m:
                    i = -4 if m[1] == "target" else -3
                else:
                    i = -2
            msg = "\n  ".join(logs[i:])

        elif msg0.startswith("Error splitting the argument list: "):
            msg = f"{logs[-2]}\n  {msg0}"
        elif msg0.startswith("Error parsing global options:"):
            if logs[-2].endswith("Invalid argument"):
                msg = "\n  ".join(logs[-3:])
            else:
                msg = f"{logs[-2]}\n  {msg0}"
        elif msg0.startswith("Error selecting an encoder for stream "):
            msg = "\n  ".join(logs[-2:])
        elif msg0 == "Conversion failed!":
            msg0 = logs[-2]
            iend = -1  # skip the last 2 lines
            if msg0.startswith("Error while processing the decoded data for stream "):
                iend = -2  # skip the last 2 lines
                i = -3  # show
                if (
                    logs[-3]
                    == "Failed to inject frame into filter network: Invalid argument"
                ):
                    i = -4
                    if logs[i] == "Error reinitializing filters!":
                        iend = -4
                        i = -5
                msg = "\n  ".join(logs[i:iend])
            elif msg0.startswith("Error initializing output stream "):
                # Could not write header for output file
                msg = "\n  ".join(logs[-4:iend])
        elif msg0.startswith("Device setup failed for decoder on input stream "):
            re_clue = re.compile(r"\[.+?\]|Device creation failed: ")
            err = next((m for m in reversed(logs[:-1]) if re_clue.match(m)), None)
            if err:
                msg = f"{err}\n  {msg0}"
        elif msg0.startswith("Supported hwaccels: "):
            msg = f"{logs[-2]}\n  {msg0}"
        elif re.match(r".+?: Invalid argument", msg0):
            msg = (
                f"{logs[-2]}\n  {msg0}" if logs[-2].startswith("[lavfi ") else logs[-2]
            )  # ...
    return msg


class FFmpegError(FFmpegioError, RuntimeError):
    def __init__(self, logs=None, log_shown=None):
        if logs is None or not len(logs):
            msg = "FFmpeg failed for unknown reason (no log available)."
        else:
            msg = scan_stderr(logs)

        if log_shown:
            ffmpeg_msg = "FFmpeg failed. Check its log printed above."
            msg = ""
        else:
            ffmpeg_msg = f"""FFmpeg terminated abnormally with the error:

  {msg}

To display the full FFmpeg log, use additional argument `show_log=True`."""

        super().__init__(ffmpeg_msg)
        self.ffmpeg_msg = msg
