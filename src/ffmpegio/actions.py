"""ffmpegio.macro - Macro plugin handler

Users can create plugin macro modules to load their often-use FFmpeg commands automatically whenever
ffmpegio package is imported.

The plugin module shall create `macro` hook(s):



"""

from . import plugins


def __getattr__(name):  # per PEP 562
    fnc = plugins.get_hook().find_action(name=name)
    if fnc is None:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    return fnc


def __dir__():
    all_names = set()
    for names in plugins.get_hook().list_actions():
        all_names.update(names)

    return [*sorted(all_names)]
