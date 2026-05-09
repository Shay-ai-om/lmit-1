from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import zipfile

from lmit.config import OcrConfig


OOXML_MEDIA_PREFIXES = {
    ".docx": "word/media/",
    ".pptx": "ppt/media/",
    ".xlsx": "xl/media/",
}

OCR_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


class PaddleOcrProvider:
    def __init__(self, cfg: OcrConfig):
        self.cfg = cfg
        self.requested_device = cfg.paddle_device
        self.resolved_device, self.device_resolution_reason = _resolve_paddle_device(cfg)
        self._backend = _build_profile_backend(cfg, resolved_device=self.resolved_device)
        self.profile_name = self._backend.profile_name

    def convert_pdf_to_markdown(self, path: Path) -> str:
        return self._backend.convert_pdf_to_markdown(path)

    def extract_embedded_image_markdown(self, path: Path) -> str:
        return self._backend.extract_embedded_image_markdown(path)


def _build_profile_backend(cfg: OcrConfig, *, resolved_device: str):
    profile = str(cfg.paddle_profile).strip().lower()
    if profile == "pp_structure":
        return _PpStructureProfile(cfg, resolved_device=resolved_device)
    if profile == "vision":
        return _VisionProfile(cfg, resolved_device=resolved_device)
    return _PpOcrProfile(cfg, resolved_device=resolved_device)


class _PpOcrProfile:
    profile_name = "pp_ocr"

    def __init__(self, cfg: OcrConfig, *, resolved_device: str):
        self.cfg = cfg
        self.resolved_device = resolved_device
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR OCR provider is enabled but `paddleocr` is not installed. "
                "Install with `pip install -e .[paddleocr]` and install PaddlePaddle "
                "for your platform separately."
            ) from exc

        try:
            import pypdfium2
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR OCR provider is enabled but `pypdfium2` is not installed. "
                "Install with `pip install -e .[paddleocr]`."
            ) from exc

        self._ocr_cls = PaddleOCR
        self._pdfium = pypdfium2
        self._engine: Any | None = None

    def convert_pdf_to_markdown(self, path: Path) -> str:
        document = self._pdfium.PdfDocument(str(path))
        sections: list[str] = [
            "# PDF OCR Result",
            "",
            f"Source: {path.name}",
        ]
        try:
            page_count = len(document)
            if page_count == 0:
                sections.extend(["", "[NO_PAGES_DETECTED]"])
                return "\n".join(sections).strip() + "\n"

            for index in range(page_count):
                page = document[index]
                try:
                    page_text = self._ocr_pdf_page(page, page_number=index + 1)
                finally:
                    _close_if_possible(page)
                sections.extend(
                    [
                        "",
                        f"## Page {index + 1}",
                        "",
                        page_text or "[NO_TEXT_DETECTED]",
                    ]
                )
        finally:
            _close_if_possible(document)

        return "\n".join(sections).strip() + "\n"

    def extract_embedded_image_markdown(self, path: Path) -> str:
        media_prefix = OOXML_MEDIA_PREFIXES.get(path.suffix.lower())
        if media_prefix is None:
            return ""

        with zipfile.ZipFile(path) as archive:
            media_names = [
                name
                for name in archive.namelist()
                if name.startswith(media_prefix)
                and Path(name).suffix.lower() in OCR_IMAGE_SUFFIXES
            ]
            if not media_names:
                return ""

            sections = ["## OCR from Embedded Images"]
            for index, name in enumerate(media_names, start=1):
                try:
                    text = self._ocr_image_bytes(archive.read(name), source_name=name)
                except Exception as exc:
                    sections.extend(
                        [
                            "",
                            f"### Image {index}: {name}",
                            "",
                            "[OCR_FAILED]",
                            "",
                            "- PaddleOCR failed on this embedded image.",
                            f"- Error: {exc!r}",
                        ]
                    )
                    continue

                sections.extend(
                    [
                        "",
                        f"### Image {index}: {name}",
                        "",
                        text or "[NO_TEXT_DETECTED]",
                    ]
                )

        return "\n".join(sections).strip()

    def _engine_instance(self):
        if self._engine is None:
            kwargs: dict[str, Any] = {
                "lang": self.cfg.paddle_lang,
                "device": self.resolved_device,
                "enable_hpi": self.cfg.paddle_enable_hpi,
                "use_tensorrt": self.cfg.paddle_use_tensorrt,
                "precision": self.cfg.paddle_precision,
                "cpu_threads": self.cfg.paddle_cpu_threads,
            }
            if self.cfg.paddle_use_angle_cls:
                kwargs["use_angle_cls"] = True
            try:
                self._engine = self._ocr_cls(**kwargs)
            except TypeError:
                kwargs.pop("use_angle_cls", None)
                self._engine = self._ocr_cls(**kwargs)
        return self._engine

    def _ocr_pdf_page(self, page, *, page_number: int) -> str:
        scale = max(float(self.cfg.paddle_pdf_render_dpi) / 72.0, 1.0)
        bitmap = page.render(scale=scale)
        try:
            image = _bitmap_to_image_input(bitmap)
            return self._ocr_image_input(image, source_name=f"page-{page_number}")
        finally:
            _close_if_possible(bitmap)

    def _ocr_image_bytes(self, image_bytes: bytes, *, source_name: str) -> str:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR OCR provider requires Pillow support to decode embedded images."
            ) from exc

        with Image.open(BytesIO(image_bytes)) as image:
            return self._ocr_image_input(image.convert("RGB"), source_name=source_name)

    def _ocr_image_input(self, image_input, *, source_name: str) -> str:
        engine = self._engine_instance()
        result: Any

        if hasattr(engine, "ocr"):
            try:
                result = engine.ocr(image_input, cls=self.cfg.paddle_use_angle_cls)
            except TypeError:
                result = engine.ocr(image_input)
        elif hasattr(engine, "predict"):
            result = engine.predict(image_input)
        else:
            raise RuntimeError(
                "Unsupported PaddleOCR runtime: expected `ocr()` or `predict()` method."
            )

        text = _extract_text(result)
        return text.strip()


class _PaddleXMarkdownProfile:
    profile_name = ""
    pipeline_name = ""

    def __init__(self, cfg: OcrConfig, *, resolved_device: str):
        self.cfg = cfg
        self.resolved_device = resolved_device
        try:
            from paddlex import create_pipeline
        except ImportError as exc:
            raise RuntimeError(
                f"PaddleOCR profile `{self.profile_name}` requires `paddlex`. "
                "Install it with `pip install -e .[paddleocr]` so `paddlex[ocr]` "
                "is available, and ensure the matching Paddle runtime is available "
                "for your platform."
            ) from exc

        self._create_pipeline = create_pipeline
        self._pipeline: Any | None = None

    def convert_pdf_to_markdown(self, path: Path) -> str:
        results = self._pipeline_instance().predict(
            input=str(path),
            **self._predict_kwargs(),
        )
        return _results_to_markdown(
            self._pipeline_instance(),
            results,
            prefer_pipeline_concatenation=True,
        )

    def extract_embedded_image_markdown(self, path: Path) -> str:
        media_prefix = OOXML_MEDIA_PREFIXES.get(path.suffix.lower())
        if media_prefix is None:
            return ""

        with zipfile.ZipFile(path) as archive:
            media_names = [
                name
                for name in archive.namelist()
                if name.startswith(media_prefix)
                and Path(name).suffix.lower() in OCR_IMAGE_SUFFIXES
            ]
            if not media_names:
                return ""

            sections = ["## OCR from Embedded Images"]
            for index, name in enumerate(media_names, start=1):
                try:
                    text = self._ocr_embedded_image_bytes(
                        archive.read(name),
                        source_name=name,
                    )
                except Exception as exc:
                    sections.extend(
                        [
                            "",
                            f"### Image {index}: {name}",
                            "",
                            "[OCR_FAILED]",
                            "",
                            f"- {self.profile_name} failed on this embedded image.",
                            f"- Error: {exc!r}",
                        ]
                    )
                    continue

                sections.extend(
                    [
                        "",
                        f"### Image {index}: {name}",
                        "",
                        text or "[NO_TEXT_DETECTED]",
                    ]
                )

        return "\n".join(sections).strip()

    def _pipeline_instance(self):
        if self._pipeline is None:
            self._pipeline = self._create_pipeline(
                pipeline=self.pipeline_name,
                device=self.resolved_device,
                use_hpip=self.cfg.paddle_enable_hpi,
            )
        return self._pipeline

    def _predict_kwargs(self) -> dict[str, Any]:
        raise NotImplementedError

    def _ocr_embedded_image_bytes(self, image_bytes: bytes, *, source_name: str) -> str:
        suffix = Path(source_name).suffix.lower() or ".png"
        with TemporaryDirectory(prefix=f"lmit-{self.profile_name}-") as tmp_dir:
            temp_path = Path(tmp_dir) / f"embedded{suffix}"
            temp_path.write_bytes(image_bytes)
            results = self._pipeline_instance().predict(
                input=str(temp_path),
                **self._predict_kwargs(),
            )
            return _results_to_markdown(self._pipeline_instance(), results).strip()


class _PpStructureProfile(_PaddleXMarkdownProfile):
    profile_name = "pp_structure"
    pipeline_name = "PP-StructureV3"

    def _predict_kwargs(self) -> dict[str, Any]:
        return {
            "use_doc_orientation_classify": (
                self.cfg.paddle_structure_use_doc_orientation_classify
            ),
            "use_chart_recognition": self.cfg.paddle_structure_use_chart_recognition,
            "merge_layout_blocks": self.cfg.paddle_structure_merge_layout_blocks,
        }


class _VisionProfile(_PaddleXMarkdownProfile):
    profile_name = "vision"
    pipeline_name = "PaddleOCR-VL"

    def _predict_kwargs(self) -> dict[str, Any]:
        return {
            "use_doc_preprocessor": self.cfg.paddle_vision_use_doc_preprocessor,
            "format_block_content": self.cfg.paddle_vision_format_block_content,
            "merge_layout_blocks": self.cfg.paddle_vision_merge_layout_blocks,
        }


def _results_to_markdown(
    pipeline,
    results: Any,
    *,
    prefer_pipeline_concatenation: bool = False,
) -> str:
    markdown_pages = [_coerce_markdown_info(result) for result in results]
    if not markdown_pages:
        return ""

    concatenate = getattr(pipeline, "concatenate_markdown_pages", None)
    if callable(concatenate) and (prefer_pipeline_concatenation or len(markdown_pages) > 1):
        return str(concatenate(markdown_pages)).strip()

    if len(markdown_pages) == 1:
        return (_markdown_text(markdown_pages[0]) or "").strip()

    parts = [_markdown_text(page).strip() for page in markdown_pages if _markdown_text(page).strip()]
    return "\n\n".join(parts).strip()


def _coerce_markdown_info(result: Any) -> dict[str, Any]:
    markdown = getattr(result, "markdown", None)
    if markdown is None and isinstance(result, dict):
        markdown = result.get("markdown")
    if markdown is None:
        return {}
    if isinstance(markdown, dict):
        return markdown
    if hasattr(markdown, "__dict__"):
        return vars(markdown)
    return {}


def _markdown_text(markdown: dict[str, Any]) -> str:
    value = markdown.get("text")
    if isinstance(value, str):
        return value
    value = markdown.get("markdown_text")
    if isinstance(value, str):
        return value
    return ""


def _bitmap_to_image_input(bitmap):
    if hasattr(bitmap, "to_numpy"):
        return bitmap.to_numpy()
    if hasattr(bitmap, "to_ndarray"):
        return bitmap.to_ndarray()
    if hasattr(bitmap, "to_pil"):
        return bitmap.to_pil().convert("RGB")
    raise RuntimeError(
        "Unsupported PDF render output from pypdfium2: expected to_numpy(), "
        "to_ndarray(), or to_pil()."
    )


def _extract_text(result: Any) -> str:
    texts: list[str] = []
    _collect_text(result, texts)
    cleaned = [text.strip() for text in texts if isinstance(text, str) and text.strip()]
    return "\n".join(cleaned)


def _collect_text(value: Any, texts: list[str]) -> None:
    if value is None:
        return

    if isinstance(value, dict):
        rec_texts = value.get("rec_texts")
        if isinstance(rec_texts, list):
            for item in rec_texts:
                if isinstance(item, str) and item.strip():
                    texts.append(item)
        rec_text = value.get("rec_text")
        if isinstance(rec_text, str) and rec_text.strip():
            texts.append(rec_text)
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
        for item in value.values():
            _collect_text(item, texts)
        return

    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[1], (list, tuple)):
            candidate = value[1]
            if candidate and isinstance(candidate[0], str) and candidate[0].strip():
                texts.append(candidate[0])
                return
        for item in value:
            _collect_text(item, texts)
        return

    if hasattr(value, "res"):
        _collect_text(getattr(value, "res"), texts)
        return

    if hasattr(value, "__dict__"):
        _collect_text(vars(value), texts)


def _close_if_possible(value: Any) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        close()


def _resolve_paddle_device(cfg: OcrConfig) -> tuple[str, str]:
    requested = str(cfg.paddle_device).strip().lower() or "auto"

    if requested != "auto":
        _validate_device_acceleration_combo(cfg, requested)
        return requested, "explicit"

    try:
        import paddle
    except ImportError:
        resolved = "cpu"
        _validate_device_acceleration_combo(cfg, resolved)
        return resolved, "paddle_unavailable"

    device_api = getattr(paddle, "device", None)
    is_compiled_with_cuda = getattr(device_api, "is_compiled_with_cuda", None)
    cuda_api = getattr(device_api, "cuda", None)
    device_count = getattr(cuda_api, "device_count", None)

    if callable(is_compiled_with_cuda) and is_compiled_with_cuda():
        count = 0
        if callable(device_count):
            try:
                count = int(device_count())
            except Exception:
                count = 0
        if count > 0:
            resolved = "gpu:0"
            _validate_device_acceleration_combo(cfg, resolved)
            return resolved, "cuda_available"

    resolved = "cpu"
    _validate_device_acceleration_combo(cfg, resolved)
    return resolved, "no_cuda"


def _validate_device_acceleration_combo(cfg: OcrConfig, resolved_device: str) -> None:
    is_gpu = str(resolved_device).lower().startswith("gpu")
    if cfg.paddle_precision == "fp16" and not is_gpu:
        raise RuntimeError("PaddleOCR fp16 precision requires a GPU device.")
    if cfg.paddle_use_tensorrt and not is_gpu:
        raise RuntimeError("PaddleOCR TensorRT requires a GPU device.")
