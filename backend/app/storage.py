"""
Local file storage manager for datasets.
"""

from __future__ import annotations

import os
from pathlib import Path


class LocalStorage:
    def __init__(self, base_dir: str = "./storage_data") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, content: bytes) -> str:
        """Save bytes content to local storage directory and return the relative path."""
        file_path = self.base_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)
        return str(file_path)

    def load(self, relative_path: str) -> bytes:
        """Load bytes content from given storage path."""
        path = Path(relative_path)
        if not path.is_absolute():
            path = Path(".") / path
        if not path.exists():
            raise FileNotFoundError(f"Storage file not found: {relative_path}")
        with open(path, "rb") as f:
            return f.read()

    def delete(self, relative_path: str) -> bool:
        """Delete storage file if exists."""
        path = Path(relative_path)
        if not path.is_absolute():
            path = Path(".") / path
        if path.exists():
            os.remove(path)
            return True
        return False


_storage_instance: LocalStorage | None = None


def get_storage() -> LocalStorage:
    """Return singleton instance of LocalStorage."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = LocalStorage()
    return _storage_instance
