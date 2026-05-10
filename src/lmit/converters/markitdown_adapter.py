from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path
from typing import Any
import requests

from lmit.config import MarkItDownConfig
from lmit.converters.markitdown_llm import (
    build_markitdown_llm_runtime,
    build_markitdown_plugin_llm_runtime,
)


DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
ACCEPT_HEADER = "text/markdown, text/html;q=0.9, text/plain;q=0.8, */*;q=0.1"


class _TimeoutSession(requests.Session):
    def __init__(self, timeout_seconds: float):
        super().__init__()
        self._timeout_seconds = float(timeout_seconds)
        self.headers.update({"Accept": ACCEPT_HEADER})

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self._timeout_seconds)
        return super().request(method, url, **kwargs)


def build_requests_session(
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> requests.Session:
    return _TimeoutSession(timeout_seconds)


class MarkItDownAdapter:
    def __init__(
        self,
        *,
        enable_plugins: bool = True,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        llm_config: MarkItDownConfig | None = None,
    ):
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise RuntimeError(
                "MarkItDown is not installed. Install the project dependencies first."
            ) from exc
        self._plugins_requested = bool(enable_plugins)
        self._plugin_names = _installed_markitdown_plugin_names()
        session = build_requests_session(request_timeout_seconds)
        kwargs: dict[str, Any] = {
            "enable_plugins": False,
            "requests_session": session,
        }
        image_llm_runtime = build_markitdown_llm_runtime(
            llm_config or MarkItDownConfig(),
            session=session,
            timeout_seconds=request_timeout_seconds,
        )
        if image_llm_runtime is not None:
            kwargs["llm_client"] = image_llm_runtime.client
            kwargs["llm_model"] = image_llm_runtime.model
            if image_llm_runtime.prompt is not None:
                kwargs["llm_prompt"] = image_llm_runtime.prompt
        plugin_llm_runtime = build_markitdown_plugin_llm_runtime(
            llm_config or MarkItDownConfig(),
            session=session,
            timeout_seconds=request_timeout_seconds,
        )
        self._image_llm_runtime_enabled = image_llm_runtime is not None
        self._plugin_llm_runtime_enabled = plugin_llm_runtime is not None
        self._md = MarkItDown(
            **kwargs,
        )
        if self._plugins_requested:
            _register_markitdown_plugins(
                self._md,
                llm_runtime=plugin_llm_runtime,
            )

    def convert_path(self, path: Path) -> str:
        return _result_text(self._md.convert(str(path)))

    def convert_url(self, url: str) -> str:
        return _result_text(self._md.convert(url))

    def plugin_diagnostics(self) -> dict[str, Any]:
        return {
            "plugins_requested": self._plugins_requested,
            "plugin_names": self._plugin_names,
            "ocr_plugin_available": "ocr" in self._plugin_names,
            "image_llm_runtime_enabled": self._image_llm_runtime_enabled,
            "plugin_llm_runtime_enabled": self._plugin_llm_runtime_enabled,
            "ocr_ready": (
                self._plugins_requested
                and self._plugin_llm_runtime_enabled
                and "ocr" in self._plugin_names
            ),
        }


def _result_text(result: Any) -> str:
    if hasattr(result, "text_content"):
        return str(result.text_content)
    return str(result)


def _installed_markitdown_plugin_names() -> tuple[str, ...]:
    try:
        return tuple(sorted(ep.name for ep in entry_points(group="markitdown.plugin")))
    except Exception:
        return ()


def _register_markitdown_plugins(md: Any, *, llm_runtime: Any | None) -> None:
    for plugin in _load_markitdown_plugins():
        kwargs: dict[str, Any] = {}
        if llm_runtime is not None:
            kwargs["llm_client"] = llm_runtime.client
            kwargs["llm_model"] = llm_runtime.model
            if llm_runtime.prompt is not None:
                kwargs["llm_prompt"] = llm_runtime.prompt
        plugin.register_converters(md, **kwargs)


def _load_markitdown_plugins() -> tuple[Any, ...]:
    plugins: list[Any] = []
    for ep in entry_points(group="markitdown.plugin"):
        try:
            plugins.append(ep.load())
        except Exception:
            continue
    return tuple(plugins)
