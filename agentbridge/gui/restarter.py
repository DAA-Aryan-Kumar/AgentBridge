"""The detached restart helper (V113) — ``python -m agentbridge.gui.restarter``.

Spawned by ``/api/app_restart`` right before the GUI server shuts itself
down. It outlives its parent on purpose (detached process group): waits for
the old GUI to exit, clears any leftover fleet processes, and relaunches
the GUI (and the harness, if one was running) with the same interpreter.

Scope guard: the restart only touches its OWN instance's processes. The
main fleet runs ``-m agentbridge.gui``/``-m agentbridge.harness`` on the
remembered defaults (no ``--home``), while dev rigs and tests always pass
``--home <dir>`` — so a main-app restart skips anything with ``--home``,
and a rig restart (its args carry ``--home``) touches ONLY processes
naming that same home, never the real fleet. A scoped (rig) restart also
skips the ``harness --all`` relaunch: rigs run per-agent harnesses their
own scripts own.

The relaunched GUI always gets ``--no-browser``: the Edge app window
outlives the server and reconnects on its own — spawning a second window
here would double it.

Process enumeration shells out to PowerShell (an OS facility, not a
runtime dependency) with ``CREATE_NO_WINDOW`` — the V119 report was a
console flashing up mid-restart (a detached process has no console, so
its child powershell CREATED one). Non-Windows falls back to ``ps``.

Relaunches use the checkout's OWN venv ``pythonw`` when it exists
(``<cwd>/.venv/Scripts/pythonw.exe``) — the canonical fleet shape —
rather than ``sys.executable``, which inside the uv-shim fleet is the
BARE uv ``python.exe`` and produced a non-canonical process chain
(V119's restart death was in such a chain). Every step appends to
``%TEMP%/agentbridge_restart.log`` so the next failure isn't a black
box. Everything is best-effort: worst case the helper relaunches beside
a process that refused to die, and the port lock (R45) resolves it.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

__all__ = ["main"]

_FLEET_MARKS = ("-m agentbridge.gui", "-m agentbridge.harness")
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def _log(msg: str) -> None:
    try:
        with open(Path(tempfile.gettempdir()) / "agentbridge_restart.log",
                  "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{os.getpid()}] "
                     f"{msg}\n")
    except OSError:
        pass


def _list_python_procs() -> list[tuple[int, str]]:
    """[(pid, command line)] for python processes, best-effort."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\""
                 " | ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                capture_output=True, text=True, timeout=30,
                creationflags=_NO_WINDOW).stdout
        else:
            out = subprocess.run(["ps", "-eo", "pid=,args="],
                                 capture_output=True, text=True,
                                 timeout=30).stdout
        procs = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            pid_s, _, cmd = line.partition("\t" if "\t" in line else " ")
            try:
                procs.append((int(pid_s), cmd.strip()))
            except ValueError:
                continue
        return procs
    except Exception:  # noqa: BLE001 — enumeration is best-effort
        return []


def _fleet_procs(scope_home: str = "") -> list[tuple[int, str]]:
    me = os.getpid()
    out = []
    for pid, cmd in _list_python_procs():
        if pid == me or "restarter" in cmd:
            continue
        if not any(m in cmd for m in _FLEET_MARKS):
            continue
        if scope_home:
            if scope_home not in cmd:
                continue          # a rig restart touches only its own home
        elif "--home" in cmd:
            continue              # the main app never touches a rig
        out.append((pid, cmd))
    return out


def _scope_home(gui_args: list[str]) -> str:
    """The ``--home`` value in the instance's own args, if any."""
    for i, a in enumerate(gui_args):
        if a == "--home" and i + 1 < len(gui_args):
            return gui_args[i + 1]
        if a.startswith("--home="):
            return a.split("=", 1)[1]
    return ""


def _wait_gone(pid: int, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if all(p != pid for p, _ in _list_python_procs()):
            return
        time.sleep(0.5)


def _hidden_startupinfo():
    """SW_HIDE startupinfo (V122): creation FLAGS only cover the direct
    child — the uv shim's own console-subsystem grandchild inherits the
    STARTUPINFO show state instead, and a default one popped a visible
    Windows Terminal per fleet spawn (the 'terminal opens' reports).
    This is the programmatic twin of Start-Process -WindowStyle Hidden."""
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return si


def _spawn(cmd: list[str], cwd: str) -> None:
    flags = _NO_WINDOW
    if sys.platform == "win32":
        flags |= (subprocess.DETACHED_PROCESS
                  | subprocess.CREATE_NEW_PROCESS_GROUP)
    _log("spawn: " + " ".join(cmd))
    subprocess.Popen(cmd, cwd=cwd or None, creationflags=flags,
                     close_fds=True, startupinfo=_hidden_startupinfo(),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL)


def _pick_exe(cwd: str, fallback: str) -> str:
    """The checkout's own venv pythonw — the canonical fleet interpreter —
    when it exists; the caller's interpreter otherwise (V119)."""
    if cwd and sys.platform == "win32":
        venv_w = Path(cwd) / ".venv" / "Scripts" / "pythonw.exe"
        if venv_w.is_file():
            return str(venv_w)
    return fallback


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentbridge-restarter")
    ap.add_argument("--gui-pid", type=int, required=True)
    ap.add_argument("--exe", required=True, help="interpreter to relaunch with")
    ap.add_argument("--cwd", default="")
    ap.add_argument("--gui-args", default="[]",
                    help="JSON list: the old GUI's own argv[1:]")
    args = ap.parse_args(argv)

    try:
        gui_args = [str(a) for a in json.loads(args.gui_args)]
    except ValueError:
        gui_args = []
    scope = _scope_home(gui_args)
    exe = _pick_exe(args.cwd, args.exe)
    _log(f"start: gui_pid={args.gui_pid} exe={exe} cwd={args.cwd} "
         f"scope={scope or '(main)'} args={gui_args}")

    # 1. let the old GUI finish its response and exit on its own
    _wait_gone(args.gui_pid, 20.0)
    _log("old gui gone (or wait expired)")

    # 2. clear what's left of THIS instance's fleet (the harness tree, a
    #    wedged GUI)
    procs = _fleet_procs(scope)
    _log(f"fleet scan: {len(procs)} proc(s)")   # V122: pinpoint truncations
    for pid, cmd in procs:
        _log(f"kill {pid}: {cmd[:120]}")
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    _wait_gone(args.gui_pid, 5.0)
    time.sleep(1.0)  # let killed processes release their locks/ports

    # 3. relaunch: the GUI first (same args, window suppressed), then the
    #    harness. V122: the main app ALWAYS gets its harness back — the old
    #    "only if one was running" rule meant a restart could never
    #    resurrect an already-dead harness, which is exactly when the
    #    button gets pressed (the live fleet ran agentless for 40 minutes
    #    across three restarts). Scoped (rig) restarts still skip it.
    if "--no-browser" not in gui_args:
        gui_args.append("--no-browser")
    try:
        _spawn([exe, "-m", "agentbridge.gui", *gui_args], args.cwd)
        if not scope:
            time.sleep(2.0)
            _spawn([exe, "-m", "agentbridge.harness", "--all"], args.cwd)
    except Exception as e:  # noqa: BLE001 — the log is the whole point
        _log(f"RELAUNCH FAILED: {type(e).__name__}: {e}")
        return 1
    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
