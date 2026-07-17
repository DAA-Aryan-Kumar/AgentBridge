"""Compatibility entry point for ``python -m gui``.

The supported GUI server lives in ``agentbridge.gui``. Keep this tiny shim so
older local launch habits still land on the v2 app instead of the retired
bridge-era server.
"""

from agentbridge.gui.fastboot import main


if __name__ == "__main__":
    raise SystemExit(main())
