from __future__ import annotations

from pathlib import Path
import sys
import types
import zipfile

import pytest

from lmit.config import OcrConfig
from lmit.converters.paddleocr_provider import PaddleOcrProvider


def _install_fake_paddle_modules(monkeypatch, *, pdf_document_cls) -> None:
    class FakePaddleOCR:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def ocr(self, image_input, cls=True):
            return [[[[0, 0], [1, 0], [1, 1], [0, 1]], ("stub", 0.99)]]

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        types.SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )
    monkeypatch.setitem(
        sys.modules,
        "pypdfium2",
        types.SimpleNamespace(PdfDocument=pdf_document_cls),
    )


def _install_fake_paddlex(monkeypatch, *, create_pipeline) -> None:
    monkeypatch.setitem(
        sys.modules,
        "paddlex",
        types.SimpleNamespace(create_pipeline=create_pipeline),
    )


def _call_resolve_device(cfg: OcrConfig):
    from lmit.converters import paddleocr_provider as module

    return module._resolve_paddle_device(cfg)


def test_paddleocr_provider_selects_backend_from_profile(monkeypatch):
    class FakeBackend:
        profile_name = "pp_structure"

        def convert_pdf_to_markdown(self, path: Path) -> str:
            return "structure markdown"

        def extract_embedded_image_markdown(self, path: Path) -> str:
            return "embedded markdown"

    monkeypatch.setattr(
        "lmit.converters.paddleocr_provider._build_profile_backend",
        lambda cfg, resolved_device=None: FakeBackend(),
    )

    provider = PaddleOcrProvider(
        OcrConfig(provider="paddleocr", paddle_profile="pp_structure")
    )

    assert provider.profile_name == "pp_structure"
    assert provider.convert_pdf_to_markdown(Path("demo.pdf")) == "structure markdown"
    assert (
        provider.extract_embedded_image_markdown(Path("demo.docx")) == "embedded markdown"
    )


def test_paddleocr_provider_auto_device_prefers_gpu_when_cuda_is_available(monkeypatch):
    class FakePaddleDeviceCuda:
        @staticmethod
        def device_count():
            return 2

    class FakePaddleDevice:
        cuda = FakePaddleDeviceCuda()

        @staticmethod
        def is_compiled_with_cuda():
            return True

    monkeypatch.setitem(sys.modules, "paddle", types.SimpleNamespace(device=FakePaddleDevice()))

    resolved, reason = _call_resolve_device(OcrConfig(provider="paddleocr", paddle_device="auto"))

    assert resolved == "gpu:0"
    assert reason == "cuda_available"


def test_paddleocr_provider_auto_device_falls_back_to_cpu_without_cuda(monkeypatch):
    class FakePaddleDeviceCuda:
        @staticmethod
        def device_count():
            return 0

    class FakePaddleDevice:
        cuda = FakePaddleDeviceCuda()

        @staticmethod
        def is_compiled_with_cuda():
            return False

    monkeypatch.setitem(sys.modules, "paddle", types.SimpleNamespace(device=FakePaddleDevice()))

    resolved, reason = _call_resolve_device(OcrConfig(provider="paddleocr", paddle_device="auto"))

    assert resolved == "cpu"
    assert reason == "no_cuda"


def test_paddleocr_provider_formats_pdf_pages_in_order(tmp_path: Path, monkeypatch):
    captured_kwargs: dict[str, object] = {}

    class FakePage:
        def __init__(self, index: int):
            self.index = index

        def close(self):
            return None

    class FakePdfDocument:
        def __init__(self, path: str):
            self.pages = [FakePage(0), FakePage(1)]

        def __len__(self):
            return len(self.pages)

        def __getitem__(self, index: int):
            return self.pages[index]

        def close(self):
            return None

    _install_fake_paddle_modules(monkeypatch, pdf_document_cls=FakePdfDocument)
    monkeypatch.setitem(
        sys.modules,
        "paddle",
        types.SimpleNamespace(
            device=types.SimpleNamespace(
                is_compiled_with_cuda=lambda: True,
                cuda=types.SimpleNamespace(device_count=lambda: 1),
            )
        ),
    )

    provider = PaddleOcrProvider(
        OcrConfig(
            provider="paddleocr",
            paddle_device="auto",
            paddle_enable_hpi=True,
            paddle_use_tensorrt=True,
            paddle_precision="fp16",
            paddle_cpu_threads=16,
        )
    )
    captured_kwargs.update(provider._backend._engine_instance().kwargs)
    monkeypatch.setattr(
        provider._backend,
        "_ocr_pdf_page",
        lambda page, *, page_number: f"page-{page_number}-text",
    )

    result = provider.convert_pdf_to_markdown(tmp_path / "scan.pdf")

    assert "# PDF OCR Result" in result
    assert "## Page 1" in result
    assert "page-1-text" in result
    assert "## Page 2" in result
    assert "page-2-text" in result
    assert result.index("## Page 1") < result.index("## Page 2")
    assert captured_kwargs["device"] == "gpu:0"
    assert captured_kwargs["enable_hpi"] is True
    assert captured_kwargs["use_tensorrt"] is True
    assert captured_kwargs["precision"] == "fp16"
    assert captured_kwargs["cpu_threads"] == 16


def test_paddleocr_provider_extracts_embedded_image_markdown_in_archive_order(
    tmp_path: Path,
    monkeypatch,
):
    class FakePdfDocument:
        def __init__(self, path: str):
            return None

    _install_fake_paddle_modules(monkeypatch, pdf_document_cls=FakePdfDocument)

    docx_path = tmp_path / "sample.docx"
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr("word/media/image2.png", b"two")
        archive.writestr("word/media/image1.png", b"one")

    provider = PaddleOcrProvider(OcrConfig(provider="paddleocr"))
    monkeypatch.setattr(
        provider._backend,
        "_ocr_image_bytes",
        lambda image_bytes, *, source_name: f"text:{source_name}",
    )

    result = provider.extract_embedded_image_markdown(docx_path)

    assert "## OCR from Embedded Images" in result
    assert "### Image 1: word/media/image2.png" in result
    assert "text:word/media/image2.png" in result
    assert "### Image 2: word/media/image1.png" in result


def test_paddleocr_provider_embedded_image_failure_is_localized(tmp_path: Path, monkeypatch):
    class FakePdfDocument:
        def __init__(self, path: str):
            return None

    _install_fake_paddle_modules(monkeypatch, pdf_document_cls=FakePdfDocument)

    pptx_path = tmp_path / "slides.pptx"
    with zipfile.ZipFile(pptx_path, "w") as archive:
        archive.writestr("ppt/media/image1.png", b"one")
        archive.writestr("ppt/media/image2.png", b"two")

    provider = PaddleOcrProvider(OcrConfig(provider="paddleocr"))

    def fake_ocr_image_bytes(image_bytes: bytes, *, source_name: str) -> str:
        if source_name.endswith("image1.png"):
            raise RuntimeError("bad image")
        return f"text:{source_name}"

    monkeypatch.setattr(provider._backend, "_ocr_image_bytes", fake_ocr_image_bytes)

    result = provider.extract_embedded_image_markdown(pptx_path)

    assert "[OCR_FAILED]" in result
    assert "bad image" in result
    assert "text:ppt/media/image2.png" in result


def test_paddleocr_provider_returns_empty_when_no_embedded_images_exist(
    tmp_path: Path,
    monkeypatch,
):
    class FakePdfDocument:
        def __init__(self, path: str):
            return None

    _install_fake_paddle_modules(monkeypatch, pdf_document_cls=FakePdfDocument)

    xlsx_path = tmp_path / "sheet.xlsx"
    with zipfile.ZipFile(xlsx_path, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook />")

    provider = PaddleOcrProvider(OcrConfig(provider="paddleocr"))

    result = provider.extract_embedded_image_markdown(xlsx_path)

    assert result == ""


def test_paddleocr_provider_pp_structure_combines_pdf_markdown(tmp_path: Path, monkeypatch):
    captured: dict[str, object] = {}

    class FakePipeline:
        def predict(self, input, **kwargs):
            captured["predict_input"] = input
            captured["predict_kwargs"] = kwargs
            return [
                types.SimpleNamespace(markdown={"text": "page one", "images": {}}),
                types.SimpleNamespace(markdown={"text": "page two", "images": {}}),
            ]

        def concatenate_markdown_pages(self, pages):
            captured["pages"] = pages
            return "combined structure markdown"

    def fake_create_pipeline(*, pipeline, device=None, use_hpip=False):
        captured["pipeline_name"] = pipeline
        captured["device"] = device
        captured["use_hpip"] = use_hpip
        return FakePipeline()

    _install_fake_paddlex(
        monkeypatch,
        create_pipeline=fake_create_pipeline,
    )

    provider = PaddleOcrProvider(
        OcrConfig(
                provider="paddleocr",
                paddle_profile="pp_structure",
                paddle_device="gpu:1",
                paddle_enable_hpi=True,
                paddle_structure_use_doc_orientation_classify=False,
                paddle_structure_use_chart_recognition=False,
                paddle_structure_merge_layout_blocks=False,
        )
    )

    result = provider.convert_pdf_to_markdown(tmp_path / "doc.pdf")

    assert result == "combined structure markdown"
    assert captured["pipeline_name"] == "PP-StructureV3"
    assert captured["device"] == "gpu:1"
    assert captured["use_hpip"] is True
    assert captured["predict_input"] == str(tmp_path / "doc.pdf")
    assert captured["predict_kwargs"] == {
        "use_doc_orientation_classify": False,
        "use_chart_recognition": False,
        "merge_layout_blocks": False,
    }


def test_paddleocr_provider_vision_combines_pdf_markdown(tmp_path: Path, monkeypatch):
    captured: dict[str, object] = {}

    class FakePipeline:
        def predict(self, input, **kwargs):
            captured["predict_input"] = input
            captured["predict_kwargs"] = kwargs
            return [
                types.SimpleNamespace(markdown={"text": "vision page", "images": {}}),
            ]

        def concatenate_markdown_pages(self, pages):
            captured["pages"] = pages
            return "combined vision markdown"

    def fake_create_pipeline(*, pipeline, device=None, use_hpip=False):
        captured["pipeline_name"] = pipeline
        captured["device"] = device
        captured["use_hpip"] = use_hpip
        return FakePipeline()

    _install_fake_paddlex(
        monkeypatch,
        create_pipeline=fake_create_pipeline,
    )

    provider = PaddleOcrProvider(
        OcrConfig(
                provider="paddleocr",
                paddle_profile="vision",
                paddle_device="gpu:0",
                paddle_enable_hpi=True,
                paddle_vision_use_doc_preprocessor=False,
                paddle_vision_format_block_content=False,
                paddle_vision_merge_layout_blocks=False,
        )
    )

    result = provider.convert_pdf_to_markdown(tmp_path / "doc.pdf")

    assert result == "combined vision markdown"
    assert captured["pipeline_name"] == "PaddleOCR-VL"
    assert captured["device"] == "gpu:0"
    assert captured["use_hpip"] is True
    assert captured["predict_input"] == str(tmp_path / "doc.pdf")
    assert captured["predict_kwargs"] == {
        "use_doc_preprocessor": False,
        "format_block_content": False,
        "merge_layout_blocks": False,
    }


def test_paddleocr_provider_requires_dependencies_when_enabled(monkeypatch):
    monkeypatch.setitem(sys.modules, "paddleocr", None)
    monkeypatch.setitem(sys.modules, "pypdfium2", None)

    with pytest.raises(RuntimeError, match="paddleocr"):
        PaddleOcrProvider(OcrConfig(provider="paddleocr"))


def test_paddleocr_provider_requires_paddlex_for_pp_structure(monkeypatch):
    monkeypatch.setitem(sys.modules, "paddlex", None)

    with pytest.raises(RuntimeError, match="paddlex"):
        PaddleOcrProvider(
            OcrConfig(provider="paddleocr", paddle_profile="pp_structure")
        )


def test_paddleocr_provider_requires_paddlex_for_vision(monkeypatch):
    monkeypatch.setitem(sys.modules, "paddlex", None)

    with pytest.raises(RuntimeError, match="paddlex"):
        PaddleOcrProvider(OcrConfig(provider="paddleocr", paddle_profile="vision"))


def test_paddleocr_provider_rejects_fp16_without_gpu(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "paddle",
        types.SimpleNamespace(
            device=types.SimpleNamespace(
                is_compiled_with_cuda=lambda: False,
                cuda=types.SimpleNamespace(device_count=lambda: 0),
            )
        ),
    )

    with pytest.raises(RuntimeError, match="fp16"):
        _call_resolve_device(
            OcrConfig(
                provider="paddleocr",
                paddle_device="cpu",
                paddle_precision="fp16",
            )
        )
