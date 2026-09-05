"""Fixed source registry: no arbitrary URL fetching or model-mediated interfaces."""
from . import players, store
from .base import Capture, SourceError
from .discovery import ADAPTERS
from .details import ADAPTERS as DETAIL_ADAPTERS

REGISTRY = {players.SOURCE: players, store.SOURCE: store, **ADAPTERS, **DETAIL_ADAPTERS}
__all__ = ["Capture", "SourceError", "REGISTRY", "players", "store"]
