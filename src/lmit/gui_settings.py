from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
import json

from lmit.config import AppConfig, load_config


DEFAULT_GUI_SETTINGS_PATH = Path("config") / "gui.settings.json"


@dataclass
class GuiSettings:
    config_path: str | None
    input_dirs: list[str]
    output_dir: str
    work_dir: str
    report_dir: str
    public_fetch_mode: str
    interval_seconds: int
    stable_seconds: int
    fetch_urls: bool
    skip_unchanged: bool
    overwrite: bool
    enrich_filenames: bool
    start_monitor_on_launch: bool
    autostart: bool
    last_run_at: str | None = None
    last_markdown_output_at: str | None = None
    last_report_path: str | None = None


def resolve_settings_path(path: Path | str | None = None, cwd: Path | None = None) -> Path:
    base = (cwd or Path.cwd()).resolve()
    raw_path = Path(path) if path is not None else DEFAULT_GUI_SETTINGS_PATH
    if not raw_path.is_absolute():
        raw_path = base / raw_path
    return raw_path.resolve()


def default_gui_settings(cwd: Path | None = None) -> GuiSettings:
    base = (cwd or Path.cwd()).resolve()
    example_config = base / "config" / "config.example.toml"
    config_path = example_config if example_config.exists() else None
    cfg = load_config(config_path, cwd=base) if config_path is not None else load_config(cwd=base)

    return GuiSettings(
        config_path=str(config_path.resolve()) if config_path is not None else None,
        input_dirs=[str(path) for path in cfg.paths.input_dirs],
        output_dir=str(cfg.paths.output_dir),
        work_dir=str(cfg.paths.work_dir),
        report_dir=str(cfg.paths.report_dir),
        public_fetch_mode=cfg.public_fetch.provider,
        interval_seconds=cfg.polling.interval_seconds,
        stable_seconds=cfg.polling.stable_seconds,
        fetch_urls=cfg.conversion.fetch_urls,
        skip_unchanged=cfg.conversion.skip_unchanged,
        overwrite=cfg.conversion.overwrite,
        enrich_filenames=cfg.output_naming.enrich_filenames,
        start_monitor_on_launch=False,
        autostart=False,
    )


def load_gui_settings(
    path: Path | str | None = None, cwd: Path | None = None
) -> GuiSettings:
    settings_path = resolve_settings_path(path, cwd)
    defaults = default_gui_settings(cwd)
    if not settings_path.exists():
        return defaults

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    merged: dict[str, Any] = asdict(defaults)
    for key, value in payload.items():
        if key in merged:
            merged[key] = value
    return _coerce_settings(merged, defaults)


def save_gui_settings(
    settings: GuiSettings, path: Path | str | None = None, cwd: Path | None = None
) -> Path:
    settings_path = resolve_settings_path(path, cwd)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return settings_path


def build_app_config_from_gui(settings: GuiSettings, cwd: Path | None = None) -> AppConfig:
    base = (cwd or Path.cwd()).resolve()
    config_path = _optional_path(settings.config_path, base)
    cfg = load_config(config_path, cwd=base) if config_path is not None else load_config(cwd=base)

    input_dirs = tuple(_resolve_user_path(item, base) for item in settings.input_dirs)
    if not input_dirs:
        raise ValueError("至少需要一個輸入資料夾")

    paths = replace(
        cfg.paths,
        input_dirs=input_dirs,
        output_dir=_resolve_user_path(settings.output_dir, base),
        work_dir=_resolve_user_path(settings.work_dir, base),
        report_dir=_resolve_user_path(settings.report_dir, base),
    )
    polling = replace(
        cfg.polling,
        enabled=True,
        interval_seconds=max(1, int(settings.interval_seconds)),
        stable_seconds=max(0, int(settings.stable_seconds)),
    )
    conversion = replace(
        cfg.conversion,
        fetch_urls=bool(settings.fetch_urls),
        skip_unchanged=bool(settings.skip_unchanged),
        overwrite=bool(settings.overwrite),
    )
    output_naming = replace(
        cfg.output_naming,
        enrich_filenames=bool(settings.enrich_filenames),
    )
    public_fetch = replace(
        cfg.public_fetch,
        provider=_normalize_public_fetch_mode(settings.public_fetch_mode, cfg.public_fetch.provider),
    )
    return replace(
        cfg,
        paths=paths,
        polling=polling,
        conversion=conversion,
        public_fetch=public_fetch,
        output_naming=output_naming,
    )


def _coerce_settings(payload: dict[str, Any], defaults: GuiSettings) -> GuiSettings:
    input_dirs = payload.get("input_dirs")
    if not isinstance(input_dirs, list):
        input_dirs = list(defaults.input_dirs)

    return GuiSettings(
        config_path=_optional_string(payload.get("config_path")),
        input_dirs=[str(item) for item in input_dirs if str(item).strip()],
        output_dir=str(payload.get("output_dir") or defaults.output_dir),
        work_dir=str(payload.get("work_dir") or defaults.work_dir),
        report_dir=str(payload.get("report_dir") or defaults.report_dir),
        public_fetch_mode=_normalize_public_fetch_mode(
            payload.get("public_fetch_mode"),
            defaults.public_fetch_mode,
        ),
        interval_seconds=max(1, _coerce_int(payload.get("interval_seconds"), defaults.interval_seconds)),
        stable_seconds=max(0, _coerce_int(payload.get("stable_seconds"), defaults.stable_seconds)),
        fetch_urls=bool(payload.get("fetch_urls")),
        skip_unchanged=bool(payload.get("skip_unchanged")),
        overwrite=bool(payload.get("overwrite")),
        enrich_filenames=bool(payload.get("enrich_filenames")),
        start_monitor_on_launch=bool(payload.get("start_monitor_on_launch")),
        autostart=bool(payload.get("autostart")),
        last_run_at=_optional_string(payload.get("last_run_at")),
        last_markdown_output_at=_optional_string(payload.get("last_markdown_output_at")),
        last_report_path=_optional_string(payload.get("last_report_path")),
    )


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_path(value: str | None, base: Path) -> Path | None:
    if not value:
        return None
    path = _resolve_user_path(value, base)
    return path if path.exists() else None


def _normalize_public_fetch_mode(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip().lower()
    if text in {"auto", "legacy"}:
        return text
    return str(fallback).strip().lower() or "auto"


def _resolve_user_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()
