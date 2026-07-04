"""Connectors — pluggable storage backends for the mesh.

Adding a backend = adding one module to this package that defines
    SCHEME = "<name>"           # how configs refer to it
    class <Anything>(Connector) # the implementation (first subclass found)
Nothing else to register: the package scans itself.

Resolution:
    get_connector("C:\\path\\to\\shared")            -> folder connector
    get_connector({"connector": "folder", "root": …}) -> by scheme
"""

import importlib
import pkgutil
from pathlib import Path

from .base import Connector, ConnectorError  # noqa: F401 (public API)

_REGISTRY = None


def registry():
    """scheme -> Connector subclass, discovered from this package's modules."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = {}
        for info in pkgutil.iter_modules(__path__):
            if info.name == "base":
                continue
            mod = importlib.import_module(f"{__name__}.{info.name}")
            scheme = getattr(mod, "SCHEME", None)
            cls = next((v for v in vars(mod).values()
                        if isinstance(v, type) and issubclass(v, Connector)
                        and v is not Connector), None)
            if scheme and cls:
                _REGISTRY[scheme] = cls
    return _REGISTRY


def get_connector(spec):
    """spec: an existing Connector (passed through), a path (folder
    connector), or a dict {"connector": scheme, ...kwargs}."""
    if isinstance(spec, Connector):
        return spec
    if isinstance(spec, (str, Path)):
        return registry()["folder"](spec)
    if isinstance(spec, dict):
        kind = spec.get("connector", "folder")
        cls = registry().get(kind)
        if not cls:
            raise ConnectorError(
                f"No connector named '{kind}' (have: {sorted(registry())})")
        kwargs = {k: v for k, v in spec.items() if k != "connector"}
        return cls(**kwargs)
    raise ConnectorError(f"Cannot build a connector from {type(spec).__name__}")
