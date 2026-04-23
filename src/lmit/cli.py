from __future__ import annotations

import argparse
from dataclasses import replace
import os
import time
from pathlib import Path
from typing import Sequence

from lmit.config import AppConfig, load_config, with_overrides
from lmit.pipeline import run_convert
from lmit.reports import (
    ConversionReport,
    load_latest_report,
    load_report,
    render_report,
    render_report_json,
)
from lmit.sessions.login import capture_session_state


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lmit")
    subparsers = parser.add_subparsers(required=True)

    convert = subparsers.add_parser("convert", help="convert input files to markdown")
    _add_common_config_args(convert)
    convert.add_argument(
        "--input",
        dest="input_dirs",
        action="append",
        help="input directory; repeat to add more roots",
    )
    convert.add_argument("--output", dest="output_dir")
    convert.add_argument("--work-dir")
    _add_conversion_runtime_args(convert)
    convert.set_defaults(func=convert_command)

    login = subparsers.add_parser("login", help="create or refresh a browser session state")
    _add_common_config_args(login)
    login.add_argument("--site", required=True)
    login.set_defaults(func=login_command)

    watch = subparsers.add_parser("watch", help="poll input and run conversion")
    _add_common_config_args(watch)
    watch.add_argument(
        "--input",
        dest="input_dirs",
        action="append",
        help="input directory; repeat to add more roots",
    )
    watch.add_argument("--output", dest="output_dir")
    watch.add_argument("--work-dir")
    _add_conversion_runtime_args(watch)
    watch.add_argument("--once", action="store_true")
    watch.set_defaults(func=watch_command)

    report = subparsers.add_parser("report", help="show conversion report diagnostics")
    _add_common_config_args(report)
    report.add_argument(
        "--report-dir",
        type=Path,
        help="directory containing conversion_report_*.json files",
    )
    report.add_argument(
        "--path",
        type=Path,
        help="specific conversion report JSON file to read",
    )
    report.add_argument(
        "--latest",
        action="store_true",
        help="read the latest conversion report JSON file; this is the default",
    )
    report.add_argument(
        "--summary",
        action="store_true",
        help="show report stats and diagnostic counts only",
    )
    report.add_argument(
        "--failed",
        action="store_true",
        help="show issue details for failed, partial, blocked, blank, and session items",
    )
    report.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable report diagnostics as JSON",
    )
    report.add_argument(
        "--log-limit",
        type=int,
        default=20,
        help="number of recent log lines to show in the default text view",
    )
    report.set_defaults(func=report_command)

    gui = subparsers.add_parser("gui", help="open the raw Markdown monitoring GUI")
    gui.add_argument("--settings", type=Path, help="GUI settings JSON path")
    gui.add_argument("--start-monitor", action="store_true")
    gui.set_defaults(func=gui_command)

    if os.environ.get("LMIT_ENABLE_EXPERIMENTAL_WIKI_CLI") == "1":
        from lmit.wiki.commands import add_wiki_subcommands

        add_wiki_subcommands(subparsers)

    return parser


def _add_common_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path)


def _add_conversion_runtime_args(parser: argparse.ArgumentParser) -> None:
    fetch_group = parser.add_mutually_exclusive_group()
    fetch_group.add_argument("--fetch-urls", action="store_true", default=None)
    fetch_group.add_argument("--no-fetch-urls", action="store_false", dest="fetch_urls")
    parser.add_argument("--overwrite", action="store_true", default=None)
    parser.add_argument("--no-skip-unchanged", action="store_false", dest="skip_unchanged")
    naming_group = parser.add_mutually_exclusive_group()
    naming_group.add_argument("--enrich-filenames", action="store_true", default=None)
    naming_group.add_argument(
        "--no-enrich-filenames",
        action="store_false",
        dest="enrich_filenames",
    )
    parser.add_argument(
        "--only",
        dest="only_patterns",
        action="append",
        help="only convert files whose relative path matches this glob; repeatable",
    )
    parser.add_argument(
        "--retry-failed",
        "--only-failed",
        dest="retry_failed",
        action="store_true",
        default=None,
        help="only retry manifest records with failed or retryable partial status",
    )


def convert_command(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    return run_convert(cfg)


def watch_command(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    cfg = replace(cfg, polling=replace(cfg.polling, enabled=True))
    print(
        "watching input dirs: "
        + ", ".join(str(path) for path in cfg.paths.input_dirs)
        + f" (interval={cfg.polling.interval_seconds}s)",
        flush=True,
    )
    while True:
        code = run_convert(cfg)
        if code != 0 or args.once:
            return code
        time.sleep(cfg.polling.interval_seconds)


def login_command(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    site = next((item for item in cfg.sessions if item.name == args.site), None)
    if site is None:
        names = ", ".join(item.name for item in cfg.sessions) or "(none)"
        print(f"Unknown site: {args.site}. Configured sites: {names}")
        return 2

    report = ConversionReport()
    capture_session_state(site, report)
    return 0


def report_command(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    try:
        if args.path is not None:
            report = load_report(args.path)
        else:
            report_dir = args.report_dir or cfg.paths.report_dir
            report = load_latest_report(report_dir)
    except Exception as exc:
        print(f"Unable to read report: {exc}")
        return 1

    if args.json:
        print(render_report_json(report), end="")
        return 0

    print(
        render_report(
            report,
            summary_only=args.summary,
            failed_only=args.failed,
            log_limit=args.log_limit,
        ),
        end="",
    )
    return 0


def gui_command(args: argparse.Namespace) -> int:
    from lmit.gui import main as gui_main

    argv: list[str] = []
    if args.settings is not None:
        argv.extend(["--settings", str(args.settings)])
    if args.start_monitor:
        argv.append("--start-monitor")
    return gui_main(argv)


def _config_from_args(args: argparse.Namespace) -> AppConfig:
    cfg = load_config(args.config)
    return with_overrides(
        cfg,
        input_dirs=getattr(args, "input_dirs", None),
        output_dir=getattr(args, "output_dir", None),
        work_dir=getattr(args, "work_dir", None),
        fetch_urls=getattr(args, "fetch_urls", None),
        overwrite=getattr(args, "overwrite", None),
        skip_unchanged=getattr(args, "skip_unchanged", None),
        enrich_filenames=getattr(args, "enrich_filenames", None),
        only_patterns=getattr(args, "only_patterns", None),
        retry_failed=getattr(args, "retry_failed", None),
    )


if __name__ == "__main__":
    raise SystemExit(main())
