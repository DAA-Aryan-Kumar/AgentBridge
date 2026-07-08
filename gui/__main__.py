"""Entry point: python -m gui [--port N] [--home DIR] [--no-browser]"""

import argparse
import socket
from pathlib import Path

from gui import __version__, server


def _instance_on_port(port, host="127.0.0.1"):
    """True if something is already serving this port. Used to avoid stacking a
    second server: ThreadingHTTPServer sets allow_reuse_address, and on Windows
    that lets duplicate binds succeed and race, so relaunching the app would
    otherwise pile up servers. A connect probe is reliable regardless of that."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def main():
    ap = argparse.ArgumentParser(
        prog="python -m gui",
        description="AgentBridge GUI — local web app in an Edge window")
    ap.add_argument("--port", type=int, default=7787)
    ap.add_argument("--home", default=None,
                    help="bridge state dir (default: %%USERPROFILE%%\\.agentbridge)")
    ap.add_argument("--no-browser", action="store_true",
                    help="serve only; do not open an app window")
    args = ap.parse_args()

    if args.home:
        server.HOME = Path(args.home)

    # single-instance guard: if AgentBridge is already up on this port, don't
    # start a second server — just open a window at the running one and exit.
    # (Quitting when the window closes is fragile with Edge --app and is left
    # to the packaging pass; this only stops duplicates from piling up.)
    if _instance_on_port(args.port):
        url = f"http://127.0.0.1:{args.port}/"
        print(f"AgentBridge GUI v{__version__} already running — opening {url}")
        if not args.no_browser:
            server.launch_window(url)
        return

    httpd = server.serve(args.port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"AgentBridge GUI v{__version__} — {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        server.launch_window(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[gui] stopped")


if __name__ == "__main__":
    main()
