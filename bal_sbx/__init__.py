try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0"

from bal_sbx.registry.json_file import JsonFileRegistry

__all__ = ["JsonFileRegistry", "__version__"]
