from json import loads
from logging import getLogger
from subprocess import CalledProcessError, check_output

LOG = getLogger("ffmpeg")


def _run(call):
    LOG.debug(f"running: {call!r}")
    try:
        return check_output(call)
    except CalledProcessError as e:
        LOG.exception(f"error while running {call!r}")
        LOG.debug(f"{e.output=}")
        LOG.debug(f"{e.stderr=}")

        # will be propagated to tracker
        raise e


def ffmpeg(*args):
    call = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        *[str(i) for i in args],
    ]
    return _run(call)


def ffprobe_json(infile):
    call = [
        "ffprobe",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-loglevel",
        "quiet",
        infile,
    ]
    return loads(_run(call).decode())
