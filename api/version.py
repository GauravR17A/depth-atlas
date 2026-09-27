"""Shared release identity for the API and compiled browser client."""

import json
from pathlib import Path

APP_VERSION: str = json.loads(Path(__file__).with_name("release.json").read_text(encoding="utf-8"))["version"]
