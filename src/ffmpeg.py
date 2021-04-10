import shlex, re, os, shutil
import subprocess as sp

# list of global options (gathered on 4/9/21)
global_options = (
    ("-y", 0),
    ("-n", 0),
    ("-cpuflags", 1),
    ("-stats", 0),
    ("-stats_period", 0),
    ("-progress", 1),
    ("-debug_ts", 0),
    ("-qphist", 0),
    ("-benchmark", 0),
    ("-benchmark_all", 0),
    ("-timelimit", 1),
    ("-dump", 0),
    ("-hex", 0),
    ("-filter_complex", 1),
    ("-filter_threads", 1),
    ("-lavfi", 1),
    ("-filter_complex_script", 1),
    ("-sdp_file", 1),
    ("-abort_on", 1),
    ("-max_error_rate", 0),
    ("-xerror", 0),
    ("-auto_conversion_filters", 0),
)

output_flags = ("-dn", "-an", "-vn", "-copyinkf", "-sn", "-bitexact", "-shortest")


def parse_options(args):
    """parse command-line option arguments

    :param args: argument string or sequence of arguments
    :type args: str or seq of str
    :return: parsed options. Flag options get None as their values.
    :rtype: dict
    """
    if isinstance(args, str):
        args = shlex.split(args)

    res = {}
    n = len(args)
    i = 0
    while i < n:
        key = args[i][1:]
        i += 1
        if i < n and args[i][0] != "-":
            res[key] = args[i]
            i += 1
        else:
            res[key] = None
    return res


def parse(cmdline):
    """Parse ffmpeg command line arguments:
    
    `[global_options] {[input_file_options] -i input_url} ... {[output_file_options] output_url} ...`
    
    Argument
    cmdline : str
        ffmpeg command line string or partial argument thereof

    Returns
        dict : parsed command fields

        dict["global_options"] : dict
        dict["inputs"] : a list of tuples for inputs: (input_url, input_file_options)
        dict["outputs"] : a list of tuples for outputs : (output_url, output_file_options)

        Any xxx_options item is a dict with the option argument (minus the leading dash, possibly with stream id) as the key and 
        its option value as the dict element value. If option is a flag, its value is None.

    Caution: multiple output_url's are detected based on the assumption that the last output file option of each output_url
    requires a value unless the option is one of the flag option listed in `output_flags`. If an unlisted flag option is used
    add it to appear as an earlier output options.

    """

    # remove multi-line command
    cmdline = re.sub(r"\\\n", " ", cmdline)

    # split the command line into its options
    args = shlex.split(cmdline)

    # exclude 'ffmpeg' command if present
    if args[0].lower() == "ffmpeg":
        args = args[1:]

    # identify -i options
    ipos = [i for i in range(len(args)) if args[i] == "-i"]
    ninputs = len(ipos)
    inputs = [None] * ninputs
    if ninputs:
        i0 = 0
        for j in range(ninputs):
            i = ipos[j]
            inputs[j] = (args[i + 1], parse_options(args[i0:i]))
            i0 = i + 2
        args = args[i0:]  # drop all input arguments

    # identify output_urls
    nargs = len(args)
    opos = (
        [
            i
            for i in range(1, nargs)
            if args[i][0] != "-"
            and (args[i - 1][0] != "-" or args[i - 1].split(":")[0] in output_flags)
        ]
        if nargs > 1
        else [0]
        if nargs > 0
        else []
    )

    noutputs = len(opos)
    outputs = [None] * noutputs
    if noutputs:
        i0 = 0
        for j in range(noutputs):
            i = opos[j]
            outputs[j] = (args[i], parse_options(args[i0:i]))
            i0 = i + 1
        args = args[i0:]  # drop all input arguments

    # identify and transfer global options
    gopts = {}
    gnames = [o[0][1:] for o in global_options]

    def extract_gopts(configs):
        for cfg in configs:
            d = cfg[1]
            keys = [key for key in d.keys() if key in gnames]
            for key in keys:
                gopts[key] = d.pop(key)

    extract_gopts(inputs)
    extract_gopts(outputs)

    return dict(global_options=gopts, inputs=inputs, outputs=outputs)


def compose(global_options={}, inputs=[], outputs=[], command="", shell_command=False):
    def opts2args(opts):
        args = []
        for key, val in opts.items():
            args.append(f"-{key}")
            if val is not None:
                args.append(str(val))
        return args

    def inputs2args(inputs):
        args = []
        for url, opts in inputs:
            if opts:
                args.extend(opts2args(opts))
            args.extend(["-i", url])
        return args

    def outputs2args(outputs):
        args = []
        for url, opts in outputs:
            if opts:
                args.extend(opts2args(opts))
            args.append(url)
        return args

    args = [
        *([command] if command else []),
        *opts2args(global_options or {}),
        *inputs2args(inputs),
        *outputs2args(outputs),
    ]

    return shlex.join(args) if shell_command else args


# add FFmpeg directory to the system path as given in system environment variable FFMPEG_DIR
FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"


def find(dir=None):
    """find ffmpeg and ffprobe in the system and sets FFMPEG_BIN and FFPROBE_BIN variables

    Linux/Mac - if not found in provided dir or in the system path, returns an error
    Windows - before returning the error, it searches additional locations:

    %PROGRAMFILES%\\ffmpeg\\bin\\ffmpeg.exe
    %PROGRAMFILES(X86)%\\ffmpeg\\bin\\ffmpeg.exe
    %APPDATA%\\ffmpeg\\bin\\ffmpeg.exe
    %LOCALAPPDATA%\\ffmpeg\\bin\\ffmpeg.exe
    %APPDATA%\\programs\\ffmpeg\\bin\\ffmpeg.exe
    %LOCALAPPDATA%\\programs\\ffmpeg\\bin\\ffmpeg.exe

    """

    global FFMPEG_BIN, FFPROBE_BIN

    dirs = ["", dir] if dir else [""]

    ext = ".exe" if os.name == "nt" else ""

    if os.name == "nt":
        dirs.extend(
            [
                os.path.join(d, "ffmpeg", "bin")
                for d in [
                    *[
                        os.environ[var]
                        for var in (
                            "PROGRAMFILES",
                            "PROGRAMFILES(X86)",
                            "USERPROFILE",
                            "APPDATA",
                            "LOCALAPPDATA",
                        )
                        if var in os.environ
                    ],
                    *[
                        os.path.join(os.environ[var], "Programs")
                        for var in ("APPDATA", "LOCALAPPDATA",)
                        if var in os.environ
                    ],
                ]
            ]
        )

    def search(cmd):
        return next(
            (p for d in dirs if (p := shutil.which(os.path.join(d, cmd + ext)))), None,
        )

    p = search("ffmpeg")
    if not p:
        raise Exception(
            "ffmpeg binary not found. Install ffmpeg & ffprobe and add their directory to the path first."
        )
    FFMPEG_BIN = p

    p = search("ffprobe")
    if not p:
        raise Exception(
            "only ffmpeg binary found and ffprobe not found. Make sure both ffmpeg and ffprobe are available on the system."
        )
    FFPROBE_BIN = p


# initialize the paths
try:
    find()
except:
    pass


def run_sync(args, *sp_arg, hide_banner=True, **sp_kwargs):

    if isinstance(args, dict):
        args = compose(**args, command=FFMPEG_BIN)
    else:
        args = [FFMPEG_BIN, *(shlex.split(args) if isinstance(args, str) else args)]

    if hide_banner:
        args.insert(1, "-hide_banner")

    return sp.run(args, *sp_arg, **sp_kwargs)


def run(args, *sp_arg, hide_banner=True, **sp_kwargs):
    if isinstance(args, dict):
        args = compose(**args, command=FFMPEG_BIN)
    else:
        args = [FFMPEG_BIN, *(shlex.split(args) if isinstance(args, str) else args)]

    if hide_banner:
        args.insert(1, "-hide_banner")

    return sp.run(args, *sp_arg, **sp_kwargs)


def ffprobe(
    args,
    *sp_arg,
    stdout=sp.PIPE,
    stderr=sp.PIPE,
    universal_newlines=True,
    encoding="utf8",
    hide_banner=True,
    **sp_kwargs,
):

    args = [
        FFPROBE_BIN,
        *(["-hide_banner"] if hide_banner else []),
        *(shlex.split(args) if isinstance(args, str) else args),
    ]
    ret = sp.run(
        args,
        *sp_arg,
        stdout=stdout,
        stderr=stderr,
        universal_newlines=universal_newlines,
        encoding=encoding,
        **sp_kwargs,
    )

    if ret.returncode != 0:
        raise Exception(f"execution failed\n   {shlex.join(args)}\n\n{ret.stderr}")
    return ret.stdout
