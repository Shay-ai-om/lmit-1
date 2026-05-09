from __future__ import annotations

from pathlib import Path

from lmit.autostart import build_autostart_command
from lmit.gui_settings import (
    GuiSettings,
    build_app_config_from_gui,
    load_gui_settings,
    save_gui_settings,
)


def test_gui_settings_round_trip(tmp_path: Path):
    settings = GuiSettings(
        config_path=None,
        input_dirs=[str(tmp_path / "inbox"), str(tmp_path / "more")],
        output_dir=str(tmp_path / "raw"),
        work_dir=str(tmp_path / "work"),
        report_dir=str(tmp_path / "reports"),
        public_fetch_mode="legacy",
        interval_seconds=45,
        stable_seconds=7,
        fetch_urls=True,
        enable_markitdown_plugins=True,
        enable_paddleocr=True,
        paddle_profile="vision",
        enable_paddle_gpu=True,
        paddle_device="gpu:1",
        enable_paddle_hpi=True,
        image_llm_enabled=True,
        image_llm_provider="openai_compatible",
        image_llm_base_url="https://api.openai.com/v1",
        image_llm_model="gpt-4.1-mini",
        image_llm_api_key_env="OPENAI_API_KEY",
        image_llm_prompt="Describe this image for Markdown.",
        skip_unchanged=True,
        overwrite=False,
        enrich_filenames=True,
        start_monitor_on_launch=True,
        autostart=False,
        last_run_at="2026-04-23 10:11:12 CST",
        last_markdown_output_at="2026-04-23 10:11:12 CST",
        last_report_path=str(tmp_path / "reports" / "conversion_report.json"),
    )

    path = save_gui_settings(settings, tmp_path / "gui.settings.json", tmp_path)
    loaded = load_gui_settings(path, tmp_path)

    assert loaded.input_dirs == settings.input_dirs
    assert loaded.interval_seconds == 45
    assert loaded.public_fetch_mode == "legacy"
    assert loaded.enable_paddleocr is True
    assert loaded.paddle_profile == "vision"
    assert loaded.enable_paddle_gpu is True
    assert loaded.paddle_device == "gpu:1"
    assert loaded.enable_paddle_hpi is True
    assert loaded.image_llm_enabled is True
    assert loaded.image_llm_provider == "openai_compatible"
    assert loaded.image_llm_model == "gpt-4.1-mini"
    assert loaded.last_markdown_output_at == "2026-04-23 10:11:12 CST"


def test_build_app_config_from_gui_applies_raw_pipeline_overrides(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    settings = GuiSettings(
        config_path=None,
        input_dirs=[str(input_dir)],
        output_dir=str(tmp_path / "output" / "raw"),
        work_dir=str(tmp_path / "work"),
        report_dir=str(tmp_path / "reports"),
        public_fetch_mode="legacy",
        interval_seconds=30,
        stable_seconds=5,
        fetch_urls=False,
        enable_markitdown_plugins=False,
        enable_paddleocr=True,
        paddle_profile="pp_structure",
        enable_paddle_gpu=True,
        paddle_device="auto",
        enable_paddle_hpi=True,
        image_llm_enabled=True,
        image_llm_provider="gemini",
        image_llm_base_url="https://generativelanguage.googleapis.com/v1beta",
        image_llm_model="gemini-2.5-flash",
        image_llm_api_key_env="GEMINI_API_KEY",
        image_llm_prompt="Describe the important text and visual layout.",
        skip_unchanged=False,
        overwrite=True,
        enrich_filenames=True,
        start_monitor_on_launch=False,
        autostart=False,
    )

    cfg = build_app_config_from_gui(settings, tmp_path)

    assert cfg.paths.input_dirs == (input_dir.resolve(),)
    assert cfg.paths.output_dir == (tmp_path / "output" / "raw").resolve()
    assert cfg.paths.report_dir == (tmp_path / "reports").resolve()
    assert cfg.polling.interval_seconds == 30
    assert cfg.polling.stable_seconds == 5
    assert cfg.public_fetch.provider == "legacy"
    assert cfg.conversion.fetch_urls is False
    assert cfg.conversion.enable_markitdown_plugins is False
    assert cfg.ocr.provider == "paddleocr"
    assert cfg.ocr.paddle_profile == "pp_structure"
    assert cfg.ocr.paddle_device == "auto"
    assert cfg.ocr.paddle_enable_hpi is True
    assert cfg.markitdown.llm_enabled is True
    assert cfg.markitdown.llm_provider == "gemini"
    assert cfg.markitdown.llm_base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert cfg.markitdown.llm_model == "gemini-2.5-flash"
    assert cfg.markitdown.llm_api_key_env == "GEMINI_API_KEY"
    assert cfg.conversion.skip_unchanged is False
    assert cfg.conversion.overwrite is True
    assert cfg.output_naming.enrich_filenames is True


def test_build_autostart_command_runs_gui_module(tmp_path: Path):
    command = build_autostart_command(
        tmp_path / "gui.settings.json",
        executable=Path("C:/Python/python.exe"),
        start_monitor=True,
    )

    assert "-m lmit.gui" in command
    assert "--settings" in command
    assert "--start-monitor" in command


def test_gui_settings_round_trip_preserves_blank_local_llm_api_env(tmp_path: Path):
    settings = GuiSettings(
        config_path=None,
        input_dirs=[str(tmp_path / "inbox")],
        output_dir=str(tmp_path / "raw"),
        work_dir=str(tmp_path / "work"),
        report_dir=str(tmp_path / "reports"),
        public_fetch_mode="auto",
        interval_seconds=30,
        stable_seconds=5,
        fetch_urls=True,
        enable_markitdown_plugins=True,
        enable_paddleocr=False,
        paddle_profile="pp_ocr",
        enable_paddle_gpu=False,
        paddle_device="auto",
        enable_paddle_hpi=False,
        image_llm_enabled=True,
        image_llm_provider="ollama",
        image_llm_base_url="",
        image_llm_model="gemma3:4b",
        image_llm_api_key_env="",
        image_llm_prompt="Describe this image.",
        skip_unchanged=True,
        overwrite=False,
        enrich_filenames=False,
        start_monitor_on_launch=False,
        autostart=False,
    )

    path = save_gui_settings(settings, tmp_path / "gui.settings.json", tmp_path)
    loaded = load_gui_settings(path, tmp_path)

    assert loaded.image_llm_provider == "ollama"
    assert loaded.image_llm_api_key_env == ""


def test_build_app_config_from_gui_disables_paddleocr_when_checkbox_is_off(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    settings = GuiSettings(
        config_path=None,
        input_dirs=[str(input_dir)],
        output_dir=str(tmp_path / "output" / "raw"),
        work_dir=str(tmp_path / "work"),
        report_dir=str(tmp_path / "reports"),
        public_fetch_mode="auto",
        interval_seconds=30,
        stable_seconds=5,
        fetch_urls=True,
        enable_markitdown_plugins=True,
        enable_paddleocr=False,
        paddle_profile="vision",
        enable_paddle_gpu=False,
        paddle_device="gpu:0",
        enable_paddle_hpi=True,
        image_llm_enabled=True,
        image_llm_provider="openai_compatible",
        image_llm_base_url="https://api.openai.com/v1",
        image_llm_model="gpt-4.1-mini",
        image_llm_api_key_env="OPENAI_API_KEY",
        image_llm_prompt="Describe this image for Markdown.",
        skip_unchanged=True,
        overwrite=False,
        enrich_filenames=False,
        start_monitor_on_launch=False,
        autostart=False,
    )

    cfg = build_app_config_from_gui(settings, tmp_path)

    assert cfg.ocr.provider == "llm"
    assert cfg.ocr.paddle_profile == "vision"
    assert cfg.ocr.paddle_device == "cpu"
    assert cfg.ocr.paddle_enable_hpi is True
