"""Vercel serverless entry point.

Vercel looks for an ASGI application named `app` in this file and routes
every /api/* request to it (see vercel.json). The application itself lives
in api.main; this module only exposes it.
"""

from api.main import app

__all__ = ["app"]
