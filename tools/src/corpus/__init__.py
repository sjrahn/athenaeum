"""corpus — the Athenaeum corpus library (ATH-CORPUS v1.0)."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("athenaeum")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
