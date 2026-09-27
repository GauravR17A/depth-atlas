"""Vercel's supported FastAPI entrypoint; local/container code uses the same app."""

from api.app import app

__all__ = ["app"]
