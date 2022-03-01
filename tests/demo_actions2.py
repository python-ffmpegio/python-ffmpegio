import ffmpegio
import pluggy

hookimpl = pluggy.HookimplMarker("ffmpegio")


def doC():
    return 'C'


def doA():
    return 'D'


@hookimpl
def list_actions():
    return ["doA", "doC"]

@hookimpl
def find_action(name):
    return {"doA": doA, "doC": doC}.get(name, None)
