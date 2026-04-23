from __future__ import annotations

from pathlib import Path

from .markitdown_adapter import MarkItDownAdapter

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
TEXT_EXTS = {".txt", ".md", ".markdown"}


def normalize_blank_text(text: str | None) -> bool:
    return text is None or text.strip() == ""


def convert_regular_file(
    file_path: Path,
    adapter: MarkItDownAdapter,
    *,
    blank_note_for_images: bool = True,
) -> tuple[str, bool]:
    suffix = file_path.suffix.lower()

    if suffix in TEXT_EXTS:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    else:
        text = adapter.convert_path(file_path)

    if not normalize_blank_text(text):
        return text, False

    if suffix in IMAGE_EXTS and blank_note_for_images:
        return (
            "# Image Conversion Result\n\n"
            f"Source: {file_path.name}\n\n"
            "[IMAGE_WITHOUT_EXTRACTED_TEXT]\n\n"
            "- MarkItDown did not extract visible text/content from this image.\n"
            "- Possible reasons: no OCR plugin, no image description provider, "
            "no metadata, or no extractable text.\n",
            True,
        )

    return (
        "# Conversion Result\n\n"
        f"Source: {file_path.name}\n\n"
        "[BLANK_OUTPUT]\n",
        True,
    )
