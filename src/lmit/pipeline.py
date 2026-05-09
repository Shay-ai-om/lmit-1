from __future__ import annotations

from collections.abc import Callable

from lmit.cancellation import ConversionCancelled
from lmit.config import AppConfig
from lmit.converters.local_file import convert_regular_file
from lmit.converters.markitdown_adapter import MarkItDownAdapter
from lmit.converters.txt_urls import convert_txt_with_urls
from lmit.conversion_key import conversion_key
from lmit.error_classification import classify_error
from lmit.file_selection import filter_scanned_files
from lmit.filename_enrichment import enriched_output_path
from lmit.fetchers.public_url import PublicUrlFetcher
from lmit.fetchers.session_url import SessionUrlFetcher
from lmit.manifest import Manifest
from lmit.path_safety import output_path_for, safe_unlink_file, safe_write_text
from lmit.reports import ConversionReport
from lmit.scanner import scan_input
from lmit.sessions.login import capture_session_state
from lmit.sessions.manager import SessionManager


def run_convert(
    cfg: AppConfig,
    *,
    capture_session=capture_session_state,
    cancel_check: Callable[[], None] | None = None,
) -> int:
    if cancel_check is None:
        cancel_check = lambda: None
    report = ConversionReport()
    cfg.paths.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.work_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.report_dir.mkdir(parents=True, exist_ok=True)
    report.enable_running_report(cfg.paths.report_dir)

    report.log("=== LMIT convert start ===")
    report.log("input_dirs = " + ", ".join(str(path) for path in cfg.paths.input_dirs))
    report.log(f"output_dir = {cfg.paths.output_dir}")
    report.log(f"work_dir = {cfg.paths.work_dir}")
    report.log(f"fetch_urls = {cfg.conversion.fetch_urls}")
    report.log(f"enrich_filenames = {cfg.output_naming.enrich_filenames}")

    try:
        files, scan_summary = scan_input(cfg)
    except Exception as exc:
        report.log(f"[FATAL] scan failed: {exc!r}")
        report.stats.failed += 1
        report.write(cfg.paths.report_dir)
        report.clear_running_report()
        return 1

    report.stats.scanned_items = scan_summary.scanned_items
    report.stats.matched_files = scan_summary.matched_files
    report.stats.skipped_unsupported = scan_summary.skipped_unsupported
    report.stats.skipped_excluded = scan_summary.skipped_excluded
    report.stats.skipped_unstable = scan_summary.skipped_unstable
    report.log(
        "scan summary: "
        f"roots={scan_summary.input_roots}, items={scan_summary.scanned_items}, "
        f"matched={scan_summary.matched_files}, "
        f"excluded={scan_summary.skipped_excluded}, unsupported={scan_summary.skipped_unsupported}, "
        f"unstable={scan_summary.skipped_unstable}"
    )
    manifest = Manifest.load(cfg.paths.work_dir / "manifest.json")
    present_manifest_keys = scan_summary.present_manifest_keys or {
        scanned.manifest_key for scanned in files
    }
    missing = manifest.mark_missing(present_manifest_keys)
    if missing:
        report.stats.manifest_missing += len(missing)
        for key_name in missing:
            report.log(f"[MISSING] {key_name}")

    if cfg.conversion.only_patterns:
        before = len(files)
        files = filter_scanned_files(files, cfg.conversion.only_patterns)
        report.stats.matched_files = len(files)
        report.log(
            "only filter: "
            f"patterns={list(cfg.conversion.only_patterns)}, matched={len(files)}/{before}"
        )
    if cfg.conversion.retry_failed:
        before = len(files)
        files = [scanned for scanned in files if manifest.is_retry_candidate(scanned)]
        report.stats.matched_files = len(files)
        report.log(f"retry failed filter: matched={len(files)}/{before}")

    key = conversion_key(cfg)
    adapter = MarkItDownAdapter(
        enable_plugins=cfg.conversion.enable_markitdown_plugins,
        llm_config=cfg.markitdown,
        ocr_config=cfg.ocr,
        log=report.log,
    )
    public_fetcher = PublicUrlFetcher(
        adapter,
        work_dir=cfg.paths.work_dir,
        report=report,
        public_fetch=cfg.public_fetch,
        cancel_check=cancel_check,
    )
    session_manager = SessionManager(cfg)
    session_fetcher = SessionUrlFetcher(
        adapter=adapter,
        work_dir=cfg.paths.work_dir,
        report=report,
        capture_session=capture_session,
        cancel_check=cancel_check,
    )

    for scanned in files:
        cancelled = False
        try:
            cancel_check()
        except ConversionCancelled:
            report.log("[CANCELLED] conversion aborted before next item")
            break
        report.log(f"[ITEM-START] {scanned.manifest_key}")
        base_out_path = output_path_for(
            scanned.source_root or cfg.paths.input_dir,
            cfg.paths.output_dir,
            scanned.path,
            scanned.output_relative_path,
        )

        if cfg.conversion.skip_unchanged and not cfg.conversion.overwrite:
            if manifest.is_unchanged_completed(
                scanned,
                conversion_key=key,
            ):
                cached_path = manifest.unchanged_completed_output_path(
                    scanned,
                    conversion_key=key,
                )
                report.stats.skipped += 1
                report.stats.skipped_unchanged += 1
                if cached_path is not None and cached_path.exists():
                    report.log(f"[SKIP-UNCHANGED] {scanned.manifest_key} -> {cached_path}")
                else:
                    report.log(f"[SKIP-UNCHANGED] {scanned.manifest_key}")
                continue

        try:
            status = "success"
            out_path = base_out_path
            previous_out_path = manifest.output_path_for(scanned)
            if scanned.suffix == ".txt":
                result = convert_txt_with_urls(
                    scanned.path,
                    fetch_urls=cfg.conversion.fetch_urls,
                    public_fetcher=public_fetcher,
                    session_fetcher=session_fetcher,
                    session_manager=session_manager,
                    report=report,
                    cancel_check=cancel_check,
                )
                text = result.markdown
                report.stats.blank_output += result.blank_count
                if result.failed_count or result.cancelled:
                    status = "partial"
                cancelled = result.cancelled
            else:
                text, blank = convert_regular_file(
                    scanned.path,
                    adapter,
                    blank_note_for_images=cfg.conversion.blank_note_for_images,
                    cancel_check=cancel_check,
                )
                if blank:
                    report.stats.blank_output += 1

            if cfg.output_naming.enrich_filenames:
                out_path = enriched_output_path(
                    base_out_path,
                    cfg.paths.output_dir,
                    text,
                    cfg.output_naming,
                )
                if out_path.resolve() != base_out_path.resolve():
                    report.stats.renamed_output_files += 1

            safe_write_text(out_path, cfg.paths.output_dir, text)
            if previous_out_path and previous_out_path.resolve() != out_path.resolve():
                safe_unlink_file(previous_out_path, cfg.paths.output_dir)
            manifest.update(
                scanned,
                out_path,
                status=status,
                conversion_key=key,
                last_error_type="url_fetch_failed" if status == "partial" else None,
                retryable=True if status == "partial" else None,
            )
            if status == "partial":
                report.stats.partial += 1
                report.log(f"[PARTIAL] {scanned.manifest_key} -> {out_path}")
            else:
                report.stats.converted += 1
                report.log(f"[OK] {scanned.manifest_key} -> {out_path}")
            if cancelled:
                report.log(f"[CANCELLED] partial output saved for {scanned.manifest_key}")
                break
        except Exception as exc:
            classification = classify_error(exc)
            manifest.update(
                scanned,
                out_path,
                status="failed",
                conversion_key=key,
                error=repr(exc),
                last_error_type=classification.error_type,
                retryable=classification.retryable,
            )
            report.stats.failed += 1
            report.log(
                f"[FAIL] {scanned.manifest_key}: {exc!r} "
                f"(type={classification.error_type}, retryable={classification.retryable})"
            )

    manifest.save()
    md_path, json_path = report.write(cfg.paths.report_dir)
    report.clear_running_report()
    report.log(f"report_md = {md_path}")
    report.log(f"report_json = {json_path}")
    report.log("=== LMIT convert done ===")
    if any("[CANCELLED]" in line for line in report.lines):
        return 130
    return 0 if report.stats.failed == 0 else 1
