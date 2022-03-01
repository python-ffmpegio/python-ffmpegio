import ffmpegio
import pluggy

hookimpl = pluggy.HookimplMarker("ffmpegio")


def doA():
    return "A"


def doB():
    return "B"


@hookimpl
def list_actions():
    return ["doA", "doB"]


@hookimpl
def find_action(name):
    return {"doA": doA, "doB": doB}.get(name, None)
