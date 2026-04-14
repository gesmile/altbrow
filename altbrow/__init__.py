# altbrow/__init__.py

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("altbrow")
except PackageNotFoundError:
    # fallback when running from source tree to minor
    __version__ = "0.1.0"
