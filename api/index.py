"""Vercel serverless entry point.

Vercel turns each .py file under /api into its own serverless function, so
this directory holds exactly one file. The application lives in `server`;
this module only exposes it as the ASGI handler Vercel looks for.
"""

from server.main import app

__all__ = ["app"]
