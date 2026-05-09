from __future__ import annotations

from pathlib import Path
import json
import sys
import types

import pytest
import requests

from lmit.config import MarkItDownConfig, OcrConfig
from lmit.converters.markitdown_adapter import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MarkItDownAdapter,
    build_requests_session,
)
from lmit.converters.markitdown_llm import (
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_LM_STUDIO_BASE_URL,
    DEFAULT_OLLAMA_BASE_URL,
    build_markitdown_llm_runtime,
)
from lmit.fetchers.public_url import PublicUrlFetcher
from lmit.reports import ConversionReport, latest_report_path


def test_build_requests_session_sets_default_timeout(monkeypatch):
    captured: dict[str, object] = {}
    session = build_requests_session(DEFAULT_REQUEST_TIMEOUT_SECONDS)

    def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["timeout"] = kwargs.get("timeout")
        return object()

    monkeypatch.setattr(requests.Session, "request", fake_request)

    session.get("https://example.com")

    assert captured == {
        "method": "GET",
        "url": "https://example.com",
        "timeout": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    }


def test_markitdown_adapter_passes_timeout_session(monkeypatch):
    captured: dict[str, object] = {}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    MarkItDownAdapter(enable_plugins=False)

    session = captured["requests_session"]
    assert captured["enable_plugins"] is False
    assert isinstance(session, requests.Session)
    assert session.headers["Accept"].startswith("text/markdown")


def test_markitdown_adapter_passes_llm_configuration(monkeypatch):
    captured: dict[str, object] = {}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setenv("TEST_OPENAI_KEY", "secret-key")

    MarkItDownAdapter(
        enable_plugins=True,
        llm_config=MarkItDownConfig(
            llm_enabled=True,
            llm_model="gpt-4.1-mini",
            llm_api_key_env="TEST_OPENAI_KEY",
            llm_prompt="Describe this image for Markdown.",
        ),
    )

    assert captured["enable_plugins"] is True
    assert captured["llm_model"] == "gpt-4.1-mini"
    assert captured["llm_prompt"] == "Describe this image for Markdown."
    assert hasattr(captured["llm_client"], "chat")


def test_markitdown_adapter_disables_plugins_when_paddleocr_is_enabled(monkeypatch):
    captured: dict[str, object] = {}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(
        "lmit.converters.markitdown_adapter._build_paddleocr_provider",
        lambda cfg: object(),
    )

    MarkItDownAdapter(
        enable_plugins=True,
        ocr_config=OcrConfig(provider="paddleocr"),
    )

    assert captured["enable_plugins"] is False


def test_build_markitdown_llm_runtime_requires_api_key_env(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)

    with pytest.raises(RuntimeError, match="API key environment variable is empty: MISSING_KEY"):
        build_markitdown_llm_runtime(
            MarkItDownConfig(
                llm_enabled=True,
                llm_model="gpt-4.1-mini",
                llm_api_key_env="MISSING_KEY",
            ),
            session=requests.Session(),
            timeout_seconds=30,
        )


def test_markitdown_adapter_routes_pdf_to_paddleocr_with_markitdown_fallback(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {"paths": []}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            captured["enable_plugins"] = kwargs["enable_plugins"]

        def convert(self, path: str):
            captured["paths"].append(path)
            return types.SimpleNamespace(text_content="fallback markdown")

    class FakePaddleProvider:
        def convert_pdf_to_markdown(self, path: Path) -> str:
            raise RuntimeError("ocr crashed")

        def extract_embedded_image_markdown(self, path: Path) -> str:
            raise AssertionError("should not run for pdf")

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(
        "lmit.converters.markitdown_adapter._build_paddleocr_provider",
        lambda cfg: FakePaddleProvider(),
    )

    logs: list[str] = []
    adapter = MarkItDownAdapter(
        enable_plugins=True,
        ocr_config=OcrConfig(provider="paddleocr"),
        log=logs.append,
    )

    result = adapter.convert_path(tmp_path / "scan.pdf")

    assert "[PADDLEOCR_PDF_FALLBACK]" in result
    assert "fallback markdown" in result
    assert any("[OCR-PROVIDER] provider=paddleocr" in line for line in logs)
    assert any("fallback=markitdown" in line for line in logs)


def test_markitdown_adapter_logs_selected_paddle_profile(monkeypatch, tmp_path: Path):
    class FakeMarkItDown:
        def __init__(self, **kwargs):
            return None

        def convert(self, path: str):
            return types.SimpleNamespace(text_content="fallback markdown")

    class FakePaddleProvider:
        profile_name = "vision"

        def convert_pdf_to_markdown(self, path: Path) -> str:
            return "vision markdown"

        def extract_embedded_image_markdown(self, path: Path) -> str:
            raise AssertionError("should not run for pdf")

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(
        "lmit.converters.markitdown_adapter._build_paddleocr_provider",
        lambda cfg: FakePaddleProvider(),
    )

    logs: list[str] = []
    adapter = MarkItDownAdapter(
        enable_plugins=True,
        ocr_config=OcrConfig(provider="paddleocr", paddle_profile="vision"),
        log=logs.append,
    )

    result = adapter.convert_path(tmp_path / "scan.pdf")

    assert result == "vision markdown"
    assert any("profile=vision" in line for line in logs)
    assert any("[OCR-DEVICE]" in line for line in logs)


def test_markitdown_adapter_keeps_standalone_images_on_markitdown_path_when_paddleocr_enabled(
    monkeypatch,
    tmp_path: Path,
):
    captured: dict[str, object] = {"paths": []}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            return None

        def convert(self, path: str):
            captured["paths"].append(path)
            return types.SimpleNamespace(text_content="image markdown")

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(
        "lmit.converters.markitdown_adapter._build_paddleocr_provider",
        lambda cfg: object(),
    )

    adapter = MarkItDownAdapter(
        enable_plugins=True,
        ocr_config=OcrConfig(provider="paddleocr"),
    )

    result = adapter.convert_path(tmp_path / "photo.png")

    assert result == "image markdown"
    assert captured["paths"] == [str(tmp_path / "photo.png")]


def test_markitdown_adapter_appends_embedded_image_ocr_for_office_docs(
    monkeypatch,
    tmp_path: Path,
):
    captured: dict[str, object] = {"paths": []}

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            return None

        def convert(self, path: str):
            captured["paths"].append(path)
            return types.SimpleNamespace(text_content="base markdown")

    class FakePaddleProvider:
        def convert_pdf_to_markdown(self, path: Path) -> str:
            raise AssertionError("should not run for docx")

        def extract_embedded_image_markdown(self, path: Path) -> str:
            return "## OCR from Embedded Images\n\nembedded text"

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    monkeypatch.setattr(
        "lmit.converters.markitdown_adapter._build_paddleocr_provider",
        lambda cfg: FakePaddleProvider(),
    )

    logs: list[str] = []
    adapter = MarkItDownAdapter(
        enable_plugins=True,
        ocr_config=OcrConfig(provider="paddleocr"),
        log=logs.append,
    )

    result = adapter.convert_path(tmp_path / "slides.pptx")

    assert result.startswith("base markdown")
    assert "## OCR from Embedded Images" in result
    assert "embedded text" in result
    assert captured["paths"] == [str(tmp_path / "slides.pptx")]
    assert any("status=appended" in line for line in logs)


def test_build_markitdown_llm_runtime_supports_lm_studio_without_api_key(monkeypatch):
    monkeypatch.delenv("LM_STUDIO_API_KEY", raising=False)

    runtime = build_markitdown_llm_runtime(
        MarkItDownConfig(
            llm_enabled=True,
            llm_provider="lm_studio",
            llm_base_url="",
            llm_model="qwen2.5-vl-7b-instruct",
            llm_api_key_env="LM_STUDIO_API_KEY",
        ),
        session=requests.Session(),
        timeout_seconds=30,
    )

    assert runtime is not None
    assert runtime.model == "qwen2.5-vl-7b-instruct"
    assert runtime.client._base_url == f"{DEFAULT_LM_STUDIO_BASE_URL}/chat/completions"


def test_gemini_client_translates_openai_style_messages(monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")

    session = requests.Session()

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "A cat sitting on a chair."},
                                ]
                            }
                        }
                    ]
                }

        return FakeResponse()

    monkeypatch.setattr(session, "post", fake_post)

    runtime = build_markitdown_llm_runtime(
        MarkItDownConfig(
            llm_enabled=True,
            llm_provider="gemini",
            llm_base_url="",
            llm_model="gemini-2.5-flash",
            llm_api_key_env="GEMINI_API_KEY",
        ),
        session=session,
        timeout_seconds=42,
    )

    response = runtime.client.chat.completions.create(
        model=runtime.model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,QUJDRA==",
                        },
                    },
                ],
            }
        ],
    )

    assert response.choices[0].message.content == "A cat sitting on a chair."
    assert captured["url"] == f"{DEFAULT_GEMINI_BASE_URL}/models/gemini-2.5-flash:generateContent"
    assert captured["headers"]["x-goog-api-key"] == "gemini-secret"
    assert captured["timeout"] == 42
    assert captured["json"] == {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Describe this image."},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": "QUJDRA==",
                        }
                    },
                ],
            }
        ]
    }


def test_ollama_client_translates_openai_style_messages(monkeypatch):
    captured: dict[str, object] = {}
    session = requests.Session()

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "content": "This looks like a handwritten receipt.",
                    }
                }

        return FakeResponse()

    monkeypatch.setattr(session, "post", fake_post)

    runtime = build_markitdown_llm_runtime(
        MarkItDownConfig(
            llm_enabled=True,
            llm_provider="ollama",
            llm_base_url="",
            llm_model="gemma3:4b",
            llm_api_key_env="",
        ),
        session=session,
        timeout_seconds=17,
    )

    response = runtime.client.chat.completions.create(
        model=runtime.model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,ZWZnaA==",
                        },
                    },
                ],
            }
        ],
    )

    assert response.choices[0].message.content == "This looks like a handwritten receipt."
    assert captured["url"] == f"{DEFAULT_OLLAMA_BASE_URL}/chat"
    assert captured["headers"] == {"Content-Type": "application/json"}
    assert captured["timeout"] == 17
    assert captured["json"] == {
        "model": "gemma3:4b",
        "messages": [
            {
                "role": "user",
                "content": "What is in this image?",
                "images": ["ZWZnaA=="],
            }
        ],
        "stream": False,
    }


def test_public_url_browser_fallback_sets_navigation_timeout(tmp_path: Path):
    captured: dict[str, object] = {}

    class FakePage:
        def goto(self, url, *, wait_until, timeout):
            captured["goto"] = {
                "url": url,
                "wait_until": wait_until,
                "timeout": timeout,
            }

        def wait_for_load_state(self, state, *, timeout):
            captured["wait_for_load_state"] = {"state": state, "timeout": timeout}

        def wait_for_timeout(self, timeout):
            captured["wait_for_timeout"] = timeout

        def content(self):
            return "<html><body>ok</body></html>"

    class FakeContext:
        def add_init_script(self, script):
            captured["init_script"] = script

        def new_page(self):
            return FakePage()

    class FakeBrowser:
        def new_context(self, **kwargs):
            captured["new_context_kwargs"] = kwargs
            return FakeContext()

        def close(self):
            captured["browser_closed"] = True

    class FakeChromium:
        def launch(self, *, headless, **kwargs):
            captured["headless"] = headless
            captured["launch_kwargs"] = kwargs
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSyncPlaywright:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_module = types.SimpleNamespace(
        TimeoutError=RuntimeError,
        sync_playwright=lambda: FakeSyncPlaywright(),
    )
    monkeypatch_modules = {"playwright.sync_api": fake_module}
    original_modules = {name: sys.modules.get(name) for name in monkeypatch_modules}
    sys.modules.update(monkeypatch_modules)
    try:
        class DummyAdapter:
            def convert_url(self, url: str) -> str:
                raise RuntimeError("primary failed")

            def convert_path(self, path: Path) -> str:
                return path.read_text(encoding="utf-8")

        fetcher = PublicUrlFetcher(
            DummyAdapter(),
            work_dir=tmp_path,
            report=ConversionReport(),
        )

        result = fetcher.fetch("https://example.com")
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    assert "ok" in result
    assert captured["goto"]["url"] == "https://example.com"
    assert captured["goto"]["wait_until"] == "domcontentloaded"
    assert captured["goto"]["timeout"] > 0
    assert captured["new_context_kwargs"] == {"locale": "zh-TW"}
    assert captured["wait_for_load_state"] == {"state": "networkidle", "timeout": 15000}
    assert captured["wait_for_timeout"] == 3000
    assert captured["browser_closed"] is True


def test_running_report_updates_without_affecting_latest_final_report(tmp_path: Path):
    report = ConversionReport()
    report.stats.converted = 1
    report.enable_running_report(tmp_path)
    report.log("[OK] alpha.txt -> alpha.md")

    running_json = tmp_path / "conversion_report_running.json"
    payload = json.loads(running_json.read_text(encoding="utf-8"))
    assert payload["stats"]["converted"] == 1
    assert payload["log"] == ["[OK] alpha.txt -> alpha.md"]

    finished = tmp_path / "conversion_report_20260425_010203.json"
    finished.write_text(json.dumps({"stats": {}, "log": []}), encoding="utf-8")

    assert latest_report_path(tmp_path) == finished
