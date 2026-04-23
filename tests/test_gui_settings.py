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
        interval_seconds=45,
        stable_seconds=7,
        fetch_urls=True,
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
        interval_seconds=30,
        stable_seconds=5,
        fetch_urls=False,
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
    assert cfg.conversion.fetch_urls is False
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
