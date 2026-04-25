from pathlib import Path
from dataclasses import replace

from lmit.config import default_config, load_config, with_overrides
from lmit.scanner import scan_input


def test_scanner_skips_default_secret_json(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "note.txt").write_text("hello", encoding="utf-8")
    (input_dir / "vertex-key.json").write_text('{"secret": true}', encoding="utf-8")

    cfg = with_overrides(default_config(tmp_path), input_dir=str(input_dir), cwd=tmp_path)
    files, summary = scan_input(cfg)

    assert [item.relative_path.as_posix() for item in files] == ["note.txt"]
    assert summary.skipped_excluded == 1


def test_scanner_namespaces_multiple_input_roots(tmp_path: Path):
    first = tmp_path / "input_a"
    second = tmp_path / "input_b"
    first.mkdir()
    second.mkdir()
    (first / "same.txt").write_text("first", encoding="utf-8")
    (second / "same.txt").write_text("second", encoding="utf-8")

    cfg = with_overrides(
        default_config(tmp_path),
        input_dirs=[str(first), str(second)],
        cwd=tmp_path,
    )

    files, summary = scan_input(cfg)

    assert summary.input_roots == 2
    assert [item.manifest_key for item in files] == [
        "input_a/same.txt",
        "input_b/same.txt",
    ]
    assert [item.output_relative_path.as_posix() for item in files] == [
        "input_a/same.txt",
        "input_b/same.txt",
    ]


def test_load_config_accepts_input_dirs(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '\n'.join(
            [
                "[paths]",
                'input_dirs = ["a", "b"]',
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.paths.input_dirs == ((tmp_path / "a").resolve(), (tmp_path / "b").resolve())


def test_load_config_accepts_output_naming(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '\n'.join(
            [
                "[output_naming]",
                "enrich_filenames = true",
                'prefix_source = "excerpt"',
                "max_prefix_chars = 32",
                'separator = " - "',
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.output_naming.enrich_filenames is True
    assert cfg.output_naming.prefix_source == "excerpt"
    assert cfg.output_naming.max_prefix_chars == 32
    assert cfg.output_naming.separator == " - "


def test_load_config_accepts_session_render_mode(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '\n'.join(
            [
                "[[sessions]]",
                'name = "facebook"',
                'domains = ["facebook.com"]',
                'login_url = "https://www.facebook.com/login"',
                'render_mode = "mobile"',
                "navigation_timeout_ms = 120000",
                "retry_count = 3",
                "retry_backoff_ms = 250",
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.sessions[0].render_mode == "mobile"
    assert cfg.sessions[0].navigation_timeout_ms == 120000
    assert cfg.sessions[0].retry_count == 3
    assert cfg.sessions[0].retry_backoff_ms == 250


def test_load_config_accepts_session_browser_profile_settings(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '\n'.join(
            [
                "[[sessions]]",
                'name = "reddit"',
                'domains = ["reddit.com"]',
                'login_url = "https://www.reddit.com/login/"',
                'browser_channel = "msedge"',
                "login_use_persistent_context = true",
                'login_persistent_profile_dir = ".lmit_work/browser_profiles/reddit"',
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.sessions[0].browser_channel == "msedge"
    assert cfg.sessions[0].login_use_persistent_context is True
    assert cfg.sessions[0].login_persistent_profile_dir == (
        tmp_path / ".lmit_work" / "browser_profiles" / "reddit"
    ).resolve()


def test_scanner_skips_unstable_files_only_when_polling_enabled(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "syncing.txt").write_text("still syncing", encoding="utf-8")

    cfg = with_overrides(default_config(tmp_path), input_dir=str(input_dir), cwd=tmp_path)
    cfg = replace(cfg, polling=replace(cfg.polling, enabled=True, stable_seconds=60))

    files, summary = scan_input(cfg)

    assert files == []
    assert summary.skipped_unstable == 1
    assert summary.present_manifest_keys == {"syncing.txt"}
