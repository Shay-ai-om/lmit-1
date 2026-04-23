from __future__ import annotations

from pathlib import Path
from typing import Any


class MarkItDownAdapter:
    def __init__(self, *, enable_plugins: bool = True):
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise RuntimeError(
                "MarkItDown is not installed. Install the project dependencies first."
            ) from exc
        self._md = MarkItDown(enable_plugins=enable_plugins)

    def convert_path(self, path: Path) -> str:
        return _result_text(self._md.convert(str(path)))

    def convert_url(self, url: str) -> str:
        return _result_text(self._md.convert(url))


def _result_text(result: Any) -> str:
    if hasattr(result, "text_content"):
        return str(result.text_content)
    return str(result)
