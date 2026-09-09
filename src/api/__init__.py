"""HTTP API for DiSan Lens.

Importing this package never loads CLIP or contacts Pinecone.  Expensive services
are created lazily by :mod:`src.api.dependencies`.
"""

from .app import create_app

__all__ = ["create_app"]
