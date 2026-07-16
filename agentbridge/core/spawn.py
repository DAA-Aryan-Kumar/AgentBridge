"""Windowless child-process kwargs (V122, leaf layer).

Every fleet process is a console-subsystem Python under the uv shim, and
on Windows 11 any console it creates opens a visible Windows Terminal.
Creation FLAGS (CREATE_NO_WINDOW) only cover the direct child — the
shim's own console grandchild inherits the STARTUPINFO show state
instead, so a default STARTUPINFO popped a terminal per spawn (the
"terminal opens even when it didn't need to" reports). SW_HIDE is the
programmatic twin of ``Start-Process -WindowStyle Hidden``.
"""

from __future__ import annotations

import subprocess
import sys

__all__ = ["windowless_kwargs"]

CREATE_NO_WINDOW = 0x08000000


def windowless_kwargs(*, detach: bool = False) -> dict:
    """Popen kwargs that keep a fleet child (and ITS console children)
    off the screen. ``detach`` adds its own process group + detached
    console — for children meant to outlive the parent."""
    if sys.platform != "win32":
        return {}
    flags = CREATE_NO_WINDOW
    if detach:
        flags |= (subprocess.DETACHED_PROCESS
                  | subprocess.CREATE_NEW_PROCESS_GROUP)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return {"creationflags": flags, "startupinfo": si}
