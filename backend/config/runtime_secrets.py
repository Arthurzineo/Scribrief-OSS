"""Read runtime credentials from a protected file or legacy environment input."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def read_secret(name: str, default: str = "") -> str:
    """Prefer a mounted secret file while rejecting ambiguous sources."""
    value = os.getenv(name)
    filename = os.getenv(f"{name}_FILE")
    if value is not None and filename:
        raise ImproperlyConfigured(f"{name} and {name}_FILE cannot both be set")
    if filename:
        try:
            return Path(filename).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise ImproperlyConfigured(f"{name}_FILE cannot be read") from exc
    return value if value is not None else default
