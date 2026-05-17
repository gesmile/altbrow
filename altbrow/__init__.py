# altbrow/__init__.py

import sys
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("altbrow")
except PackageNotFoundError:
    # fallback when running from source tree to minor
    __version__ = "0.1.0"

_LOGO   = "[o]" if sys.platform == "win32" else "☢"
APP_NAME = f"Altbr{_LOGO}w"
