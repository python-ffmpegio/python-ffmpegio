import os

# https://stackoverflow.com/questions/34504970/non-blocking-read-on-os-pipe-on-windows


class NoData(RuntimeError):
    pass


if os.name == "nt":

    import msvcrt

    from ctypes import windll, byref, GetLastError, WinError
    from ctypes.wintypes import HANDLE, DWORD, LPDWORD, BOOL

    PIPE_NOWAIT = DWORD(0x00000001)

    def _set_nonblock(pipefd):
        """pipefd is a integer as returned by os.pipe"""

        SetNamedPipeHandleState = windll.kernel32.SetNamedPipeHandleState
        SetNamedPipeHandleState.argtypes = [HANDLE, LPDWORD, LPDWORD, LPDWORD]
        SetNamedPipeHandleState.restype = BOOL

        h = msvcrt.get_osfhandle(pipefd)

        res = windll.kernel32.SetNamedPipeHandleState(h, byref(PIPE_NOWAIT), None, None)
        if res == 0:
            raise Exception(WinError())

    def _check_error(err):
        err_code = GetLastError()
        return err_code == 232


else:
    import fcntl

    def _set_nonblock(pipefd):
        fcntl.fcntl(pipefd, fcntl.F_SETFL, os.O_NONBLOCK)

    def _check_error(err):
        return isinstance(err, BlockingIOError)
        # return err.errno == errno.EAGAIN or err.errno == errno.EWOULDBLOCK


def pipe():
    r, w = os.pipe()
    _set_nonblock(r)
    return r, w


def read(fd, n):
    try:
        return os.read(fd, n)
    except OSError as error:
        if _check_error(error):
            raise NoData
        else:
            raise


if __name__ == "__main__":
    from ctypes import GetLastError

    # CreatePipe
    r, w = pipe()

    print(os.write(w, b"xxx"))
    print(os.read(r, 1024))
    try:
        print(os.write(w, b"yyy"))
        print(os.read(r, 1024))
        print(os.read(r, 1024))
    except OSError as e:
        print(dir(e), e.errno, GetLastError())
        print(WinError())
        if GetLastError() != 232:
            raise
    print(os.write(w, b"zzz"))
    print(os.read(r, 1024))
