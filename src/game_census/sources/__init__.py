"""Fixed source registry: no arbitrary URL fetching or model-mediated interfaces."""
from . import players, store
from .base import Capture, SourceError

REGISTRY = {players.SOURCE: players, store.SOURCE: store}
__all__ = ["Capture", "SourceError", "REGISTRY", "players", "store"]
