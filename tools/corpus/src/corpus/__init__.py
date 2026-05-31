"""ath-corpus — corpus tooling for ATH-CORPUS v1.0."""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("ath-corpus")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
