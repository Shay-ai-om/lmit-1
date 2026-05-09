from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Any
import requests

from lmit.config import MarkItDownConfig, OcrConfig
from lmit.converters.markitdown_llm import build_markitdown_llm_runtime
from lmit.converters.paddleocr_provider import (
    OOXML_MEDIA_PREFIXES,
    PaddleOcrProvider,
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
        ocr_config: OcrConfig | None = None,
        log: Callable[[str], None] | None = None,
    ):
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise RuntimeError(
                "MarkItDown is not installed. Install the project dependencies first."
            ) from exc
        self._ocr_config = ocr_config or OcrConfig()
        self._log = log or (lambda line: None)
        self._paddle_provider = _build_paddleocr_provider(self._ocr_config)
        session = build_requests_session(request_timeout_seconds)
        effective_enable_plugins = enable_plugins and self._ocr_config.provider != "paddleocr"
        kwargs: dict[str, Any] = {
            "enable_plugins": effective_enable_plugins,
            "requests_session": session,
        }
        llm_runtime = build_markitdown_llm_runtime(
            llm_config or MarkItDownConfig(),
            session=session,
            timeout_seconds=request_timeout_seconds,
        )
        if llm_runtime is not None:
            kwargs["llm_client"] = llm_runtime.client
            kwargs["llm_model"] = llm_runtime.model
            if llm_runtime.prompt is not None:
                kwargs["llm_prompt"] = llm_runtime.prompt
        self._md = MarkItDown(
            **kwargs,
        )

    def convert_path(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if self._ocr_config.provider != "paddleocr":
            return self._convert_with_markitdown(path)

        profile_name = getattr(self._paddle_provider, "profile_name", self._ocr_config.paddle_profile)
        requested_device = getattr(self._paddle_provider, "requested_device", self._ocr_config.paddle_device)
        resolved_device = getattr(self._paddle_provider, "resolved_device", requested_device)
        device_reason = getattr(self._paddle_provider, "device_resolution_reason", "unknown")
        if suffix == ".pdf":
            self._log(
                f"[OCR-PROVIDER] provider=paddleocr profile={profile_name} path={path}"
            )
            self._log(
                f"[OCR-DEVICE] requested={requested_device} resolved={resolved_device} "
                f"reason={device_reason}"
            )
            self._log(
                f"[PADDLEOCR-PDF] path={path} profile={profile_name} "
                f"dpi={self._ocr_config.paddle_pdf_render_dpi}"
            )
            assert self._paddle_provider is not None
            try:
                return self._paddle_provider.convert_pdf_to_markdown(path)
            except Exception as exc:
                self._log(
                    f"[PADDLEOCR-PDF] path={path} fallback=markitdown error={exc!r}"
                )
                fallback = self._convert_with_markitdown(path)
                return _prepend_warning(
                    fallback,
                    [
                        "[PADDLEOCR_PDF_FALLBACK]",
                        "",
                        "- PaddleOCR failed for this PDF and LMIT fell back to MarkItDown.",
                        f"- Error: {exc!r}",
                    ],
                )

        if suffix in OOXML_MEDIA_PREFIXES:
            self._log(
                f"[OCR-PROVIDER] provider=paddleocr profile={profile_name} path={path}"
            )
            self._log(
                f"[OCR-DEVICE] requested={requested_device} resolved={resolved_device} "
                f"reason={device_reason}"
            )
            base_text = self._convert_with_markitdown(path)
            self._log(
                f"[PADDLEOCR-EMBEDDED-IMAGE] path={path} profile={profile_name} status=start"
            )
            assert self._paddle_provider is not None
            try:
                extra = self._paddle_provider.extract_embedded_image_markdown(path)
            except Exception as exc:
                self._log(
                    f"[PADDLEOCR-EMBEDDED-IMAGE] path={path} profile={profile_name} "
                    f"status=error error={exc!r}"
                )
                warning = "\n".join(
                    [
                        "## OCR from Embedded Images",
                        "",
                        "[OCR_FAILED]",
                        "",
                        "- PaddleOCR failed while scanning embedded images in this document.",
                        f"- Error: {exc!r}",
                    ]
                )
                return _append_markdown(base_text, warning)

            if extra:
                self._log(
                    f"[PADDLEOCR-EMBEDDED-IMAGE] path={path} profile={profile_name} status=appended"
                )
                return _append_markdown(base_text, extra)

            self._log(
                f"[PADDLEOCR-EMBEDDED-IMAGE] path={path} profile={profile_name} status=no_images"
            )
            return base_text

        return self._convert_with_markitdown(path)

    def convert_url(self, url: str) -> str:
        return _result_text(self._md.convert(url))

    def _convert_with_markitdown(self, path: Path) -> str:
        return _result_text(self._md.convert(str(path)))


def _result_text(result: Any) -> str:
    if hasattr(result, "text_content"):
        return str(result.text_content)
    return str(result)


def _build_paddleocr_provider(cfg: OcrConfig) -> PaddleOcrProvider | None:
    if cfg.provider != "paddleocr":
        return None
    return PaddleOcrProvider(cfg)


def _prepend_warning(text: str, lines: list[str]) -> str:
    warning = "\n".join(lines).strip()
    body = text.strip()
    if body:
        return f"{warning}\n\n{body}\n"
    return f"{warning}\n"


def _append_markdown(base_text: str, extra_text: str) -> str:
    base = base_text.rstrip()
    extra = extra_text.strip()
    if not extra:
        return base_text
    if not base:
        return extra + "\n"
    return f"{base}\n\n{extra}\n"
