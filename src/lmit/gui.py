from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import argparse
import os
import re
import sys
import traceback

from lmit.autostart import (
    is_autostart_enabled,
    is_autostart_supported,
    set_autostart,
)
from lmit.cancellation import ConversionCancelled
from lmit.env import load_default_env
from lmit.gui_settings import (
    GuiSettings,
    build_app_config_from_gui,
    load_gui_settings,
    resolve_settings_path,
    save_gui_settings,
)
from lmit.pipeline import run_convert
from lmit.reports import load_latest_report
from lmit.sessions.login import capture_session_state


@dataclass
class LoginPromptRequest:
    site_name: str
    done_event: Event
    confirmed: bool | None = None


class QueueWriter:
    def __init__(self, queue: Queue[tuple[str, object]], stream_name: str):
        self.queue = queue
        self.stream_name = stream_name
        self.buffer = ""

    def write(self, text: str) -> int:
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line:
                self.queue.put(("log", line))
        return len(text)

    def flush(self) -> None:
        if self.buffer:
            self.queue.put(("log", self.buffer))
            self.buffer = ""


class RawMarkdownGui:
    def __init__(self, root, *, settings_path: Path, start_monitor: bool = False):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.cwd = Path.cwd().resolve()
        self.settings_path = settings_path
        self.settings = load_gui_settings(settings_path, self.cwd)
        if is_autostart_supported() and is_autostart_enabled():
            self.settings.autostart = True

        self.queue: Queue[tuple[str, object]] = Queue()
        self.stop_event = Event()
        self.worker: Thread | None = None
        self.monitoring = False
        self.busy = False

        self._build_vars()
        self._build_window()
        self._refresh_last_run_labels()
        self._refresh_buttons()
        self.root.after(100, self._drain_queue)

        if start_monitor or self.settings.start_monitor_on_launch:
            self.root.after(300, self.start_monitor)

    def _build_vars(self) -> None:
        tk = self.tk
        self.config_path_var = tk.StringVar(value=self.settings.config_path or "")
        self.output_dir_var = tk.StringVar(value=self.settings.output_dir)
        self.work_dir_var = tk.StringVar(value=self.settings.work_dir)
        self.report_dir_var = tk.StringVar(value=self.settings.report_dir)
        self.public_fetch_mode_var = tk.StringVar(value=self.settings.public_fetch_mode)
        self.interval_var = tk.IntVar(value=self.settings.interval_seconds)
        self.stable_var = tk.IntVar(value=self.settings.stable_seconds)
        self.fetch_urls_var = tk.BooleanVar(value=self.settings.fetch_urls)
        self.enable_markitdown_plugins_var = tk.BooleanVar(
            value=self.settings.enable_markitdown_plugins
        )
        self.enable_paddleocr_var = tk.BooleanVar(value=self.settings.enable_paddleocr)
        self.paddle_profile_var = tk.StringVar(value=self.settings.paddle_profile)
        self.enable_paddle_gpu_var = tk.BooleanVar(value=self.settings.enable_paddle_gpu)
        self.paddle_device_var = tk.StringVar(value=self.settings.paddle_device)
        self.enable_paddle_hpi_var = tk.BooleanVar(value=self.settings.enable_paddle_hpi)
        self.image_llm_enabled_var = tk.BooleanVar(value=self.settings.image_llm_enabled)
        self.image_llm_provider_var = tk.StringVar(value=self.settings.image_llm_provider)
        self.image_llm_base_url_var = tk.StringVar(value=self.settings.image_llm_base_url)
        self.image_llm_model_var = tk.StringVar(value=self.settings.image_llm_model)
        self.image_llm_api_key_env_var = tk.StringVar(value=self.settings.image_llm_api_key_env)
        self.image_llm_prompt_var = tk.StringVar(value=self.settings.image_llm_prompt)
        self.skip_unchanged_var = tk.BooleanVar(value=self.settings.skip_unchanged)
        self.overwrite_var = tk.BooleanVar(value=self.settings.overwrite)
        self.enrich_filenames_var = tk.BooleanVar(value=self.settings.enrich_filenames)
        self.launch_monitor_var = tk.BooleanVar(value=self.settings.start_monitor_on_launch)
        self.autostart_var = tk.BooleanVar(value=self.settings.autostart)
        self.status_var = tk.StringVar(value="閒置")
        self.next_run_var = tk.StringVar(value="尚未啟動監控")
        self.last_run_var = tk.StringVar()
        self.last_output_var = tk.StringVar()
        self.last_report_var = tk.StringVar()

    def _build_window(self) -> None:
        tk = self.tk
        ttk = self.ttk

        self.root.title("LMIT Raw Markdown 監控台")
        self.root.geometry("1040x820")
        self.root.minsize(900, 760)

        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Accent.TButton", padding=(14, 7))
        style.configure("Header.TLabel", font=("Microsoft JhengHei UI", 12, "bold"))

        outer = ttk.Frame(self.root, padding=14)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Raw Markdown 產生與監控", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, textvariable=self.status_var).grid(row=0, column=1, sticky="e")

        config_frame = ttk.Frame(outer)
        config_frame.grid(row=1, column=0, sticky="ew")
        config_frame.columnconfigure(0, weight=1)
        config_frame.columnconfigure(1, weight=1)

        paths_frame = ttk.LabelFrame(config_frame, text="路徑")
        paths_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        paths_frame.columnconfigure(0, weight=1)

        self.input_list = tk.Listbox(paths_frame, height=6, activestyle="none")
        self.input_list.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))
        for item in self.settings.input_dirs:
            self.input_list.insert(tk.END, item)

        input_buttons = ttk.Frame(paths_frame)
        input_buttons.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        ttk.Button(input_buttons, text="新增輸入資料夾", command=self.add_input_dir).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(input_buttons, text="移除選取", command=self.remove_selected_input).grid(
            row=0, column=1
        )

        self._path_row(paths_frame, 2, "輸出 raw Markdown", self.output_dir_var, self.browse_output_dir)
        self._path_row(paths_frame, 4, "工作資料夾", self.work_dir_var, self.browse_work_dir)
        self._path_row(paths_frame, 6, "報告資料夾", self.report_dir_var, self.browse_report_dir)
        self._path_row(paths_frame, 8, "基底 TOML 設定", self.config_path_var, self.browse_config_path)

        options_frame = ttk.LabelFrame(config_frame, text="監控與選項")
        options_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        options_frame.columnconfigure(1, weight=1)

        ttk.Label(options_frame, text="檢測頻率（秒）").grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 4)
        )
        ttk.Spinbox(
            options_frame,
            from_=1,
            to=86400,
            textvariable=self.interval_var,
            width=10,
        ).grid(row=0, column=1, sticky="w", padx=10, pady=(10, 4))

        ttk.Label(options_frame, text="檔案穩定秒數").grid(
            row=1, column=0, sticky="w", padx=10, pady=4
        )
        ttk.Spinbox(
            options_frame,
            from_=0,
            to=86400,
            textvariable=self.stable_var,
            width=10,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=4)

        ttk.Label(options_frame, text="Public URL mode").grid(
            row=2, column=0, sticky="w", padx=10, pady=4
        )
        ttk.Combobox(
            options_frame,
            textvariable=self.public_fetch_mode_var,
            state="readonly",
            values=("auto", "legacy"),
            width=12,
        ).grid(row=2, column=1, sticky="w", padx=10, pady=4)

        markitdown_frame = ttk.LabelFrame(options_frame, text="MarkItDown")
        markitdown_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        markitdown_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            markitdown_frame,
            text="啟用 MarkItDown plugins（OCR plugin 需要這個）",
            variable=self.enable_markitdown_plugins_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))
        ttk.Checkbutton(
            markitdown_frame,
            text="啟用圖片 LLM 描述",
            variable=self.image_llm_enabled_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(
            markitdown_frame,
            text="啟用 PaddleOCR 作為 OCR provider",
            variable=self.enable_paddleocr_var,
            command=self._sync_paddleocr_controls,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Label(markitdown_frame, text="Paddle profile").grid(
            row=2, column=0, sticky="w", padx=8, pady=3
        )
        self.paddle_profile_combo = ttk.Combobox(
            markitdown_frame,
            textvariable=self.paddle_profile_var,
            state="readonly",
            values=("pp_ocr", "pp_structure", "vision"),
            width=18,
        )
        self.paddle_profile_combo.grid(row=2, column=1, sticky="ew", padx=8, pady=3)
        ttk.Checkbutton(
            markitdown_frame,
            text="啟用 GPU 加速（若可用）",
            variable=self.enable_paddle_gpu_var,
            command=self._sync_paddleocr_controls,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Label(markitdown_frame, text="Paddle device").grid(
            row=4, column=0, sticky="w", padx=8, pady=3
        )
        self.paddle_device_combo = ttk.Combobox(
            markitdown_frame,
            textvariable=self.paddle_device_var,
            state="readonly",
            values=("auto", "gpu:0", "gpu:1"),
            width=18,
        )
        self.paddle_device_combo.grid(row=4, column=1, sticky="ew", padx=8, pady=3)
        ttk.Checkbutton(
            markitdown_frame,
            text="啟用 Paddle 高效推論 HPI",
            variable=self.enable_paddle_hpi_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Label(markitdown_frame, text="LLM provider").grid(
            row=7, column=0, sticky="w", padx=8, pady=3
        )
        ttk.Combobox(
            markitdown_frame,
            textvariable=self.image_llm_provider_var,
            state="readonly",
            values=("openai_compatible", "gemini", "lm_studio", "ollama"),
            width=18,
        ).grid(row=7, column=1, sticky="ew", padx=8, pady=3)
        self._entry_row(markitdown_frame, 8, "LLM base URL", self.image_llm_base_url_var)
        self._entry_row(markitdown_frame, 9, "LLM model", self.image_llm_model_var)
        self._entry_row(markitdown_frame, 10, "API key env var", self.image_llm_api_key_env_var)
        self._entry_row(markitdown_frame, 11, "Image prompt", self.image_llm_prompt_var)

        checks = [
            ("抓取文字檔中的 link content", self.fetch_urls_var),
            ("跳過未變更檔案", self.skip_unchanged_var),
            ("覆寫既有輸出", self.overwrite_var),
            ("用內容強化輸出檔名", self.enrich_filenames_var),
            ("開啟 GUI 後自動開始監控", self.launch_monitor_var),
            ("Windows 開機自啟並開始監控", self.autostart_var),
        ]
        for offset, (label, variable) in enumerate(checks, start=4):
            ttk.Checkbutton(options_frame, text=label, variable=variable).grid(
                row=offset, column=0, columnspan=2, sticky="w", padx=10, pady=3
            )

        status_frame = ttk.LabelFrame(options_frame, text="執行狀態")
        status_frame.grid(row=10, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 8))
        status_frame.columnconfigure(1, weight=1)
        self._status_row(status_frame, 0, "最後執行", self.last_run_var)
        self._status_row(status_frame, 1, "最後產出 Markdown", self.last_output_var)
        self._status_row(status_frame, 2, "下次檢測", self.next_run_var)
        self._status_row(status_frame, 3, "最近報告", self.last_report_var)

        buttons = ttk.Frame(outer)
        buttons.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.save_button = ttk.Button(buttons, text="儲存設定", command=self.save_settings)
        self.save_button.grid(row=0, column=0, padx=(0, 6))
        self.run_button = ttk.Button(
            buttons,
            text="立即執行一次",
            command=self.run_once,
            style="Accent.TButton",
        )
        self.run_button.grid(row=0, column=1, padx=6)
        self.start_button = ttk.Button(buttons, text="開始監控", command=self.start_monitor)
        self.start_button.grid(row=0, column=2, padx=6)
        self.stop_button = ttk.Button(buttons, text="停止 / 中止", command=self.stop_monitor)
        self.stop_button.grid(row=0, column=3, padx=6)
        ttk.Button(buttons, text="開啟輸出資料夾", command=self.open_output_dir).grid(
            row=0, column=4, padx=6
        )
        ttk.Button(buttons, text="開啟最近報告", command=self.open_latest_report).grid(
            row=0, column=5, padx=6
        )

        log_frame = ttk.LabelFrame(outer, text="執行紀錄")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self._sync_paddleocr_controls()

        self._append_log(f"設定檔：{self.settings_path}")

    def _path_row(self, parent, row: int, label: str, variable, command) -> None:
        ttk = self.ttk
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=(6, 0))
        frame = ttk.Frame(parent)
        frame.grid(row=row + 1, column=0, sticky="ew", padx=10, pady=(2, 4))
        frame.columnconfigure(0, weight=1)
        ttk.Entry(frame, textvariable=variable).grid(row=0, column=0, sticky="ew")
        ttk.Button(frame, text="選擇", command=command).grid(row=0, column=1, padx=(6, 0))

    def _status_row(self, parent, row: int, label: str, variable) -> None:
        ttk = self.ttk
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=3)
        ttk.Label(parent, textvariable=variable).grid(row=row, column=1, sticky="w", padx=8, pady=3)

    def _entry_row(self, parent, row: int, label: str, variable) -> None:
        ttk = self.ttk
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=3)

    def add_input_dir(self) -> None:
        from tkinter import filedialog

        path = filedialog.askdirectory(title="選擇輸入資料夾")
        if not path:
            return
        existing = set(self.input_list.get(0, self.tk.END))
        if path not in existing:
            self.input_list.insert(self.tk.END, path)

    def remove_selected_input(self) -> None:
        for index in reversed(self.input_list.curselection()):
            self.input_list.delete(index)

    def browse_output_dir(self) -> None:
        self._browse_directory(self.output_dir_var, "選擇輸出 raw Markdown 資料夾")

    def browse_work_dir(self) -> None:
        self._browse_directory(self.work_dir_var, "選擇工作資料夾")

    def browse_report_dir(self) -> None:
        self._browse_directory(self.report_dir_var, "選擇報告資料夾")

    def browse_config_path(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="選擇 TOML 設定檔",
            filetypes=[("TOML", "*.toml"), ("All files", "*.*")],
        )
        if path:
            self.config_path_var.set(path)

    def _browse_directory(self, variable, title: str) -> None:
        from tkinter import filedialog

        path = filedialog.askdirectory(title=title)
        if path:
            variable.set(path)

    def save_settings(self) -> None:
        try:
            self.settings = self._settings_from_ui()
            save_gui_settings(self.settings, self.settings_path, self.cwd)
            self._apply_autostart()
            self._append_log("設定已儲存")
        except Exception as exc:
            self._show_error("無法儲存設定", exc)

    def run_once(self) -> None:
        if self.busy:
            self._append_log("目前已有轉換在執行")
            return
        try:
            settings = self._settings_from_ui()
            save_gui_settings(settings, self.settings_path, self.cwd)
            self._apply_autostart()
        except Exception as exc:
            self._show_error("設定不完整", exc)
            return

        self.stop_event.clear()
        self._start_worker(self._single_run_worker, settings)

    def start_monitor(self) -> None:
        if self.monitoring:
            return
        if self.busy:
            self._append_log("請等目前執行完成後再開始監控")
            return
        try:
            settings = self._settings_from_ui()
            save_gui_settings(settings, self.settings_path, self.cwd)
            self._apply_autostart()
        except Exception as exc:
            self._show_error("設定不完整", exc)
            return

        self.monitoring = True
        self.stop_event.clear()
        self._refresh_buttons()
        self._start_worker(self._monitor_worker, settings)

    def stop_monitor(self) -> None:
        if not self.monitoring and not self.busy:
            return
        self.stop_event.set()
        self.status_var.set("正在停止")
        self._append_log("已送出停止要求，會在下一個安全中斷點停止目前這輪執行。")

    def open_output_dir(self) -> None:
        try:
            path = Path(self.output_dir_var.get()).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            _open_path(path)
        except Exception as exc:
            self._show_error("無法開啟輸出資料夾", exc)

    def open_latest_report(self) -> None:
        report_path = self.settings.last_report_path
        try:
            if report_path:
                path = Path(report_path)
            else:
                cfg = build_app_config_from_gui(self._settings_from_ui(), self.cwd)
                path = load_latest_report(cfg.paths.report_dir).path
            _open_path(path)
        except Exception as exc:
            self._show_error("找不到最近報告", exc)

    def _start_worker(self, target, settings: GuiSettings) -> None:
        self.busy = True
        self._refresh_buttons()
        self.worker = Thread(target=target, args=(settings,), daemon=True)
        self.worker.start()

    def _single_run_worker(self, settings: GuiSettings) -> None:
        try:
            self._run_convert_cycle(settings)
        finally:
            self.queue.put(("busy", False))
            self.queue.put(("status", "閒置"))

    def _monitor_worker(self, settings: GuiSettings) -> None:
        current_settings = settings
        try:
            while not self.stop_event.is_set():
                current_settings = self._run_convert_cycle(current_settings)
                if self.stop_event.is_set():
                    break
                next_run = datetime.now().astimezone() + timedelta(
                    seconds=max(1, current_settings.interval_seconds)
                )
                self.queue.put(("next_run", _format_timestamp(next_run)))
                self.queue.put(("status", "監控中"))
                if self.stop_event.wait(max(1, current_settings.interval_seconds)):
                    break
        finally:
            self.queue.put(("monitoring", False))
            self.queue.put(("busy", False))
            self.queue.put(("status", "閒置"))
            self.queue.put(("next_run", "尚未啟動監控"))

    def _run_convert_cycle(self, settings: GuiSettings) -> GuiSettings:
        self.queue.put(("status", "執行轉換中"))
        self.queue.put(("log", f"=== GUI run start {current_timestamp()} ==="))
        cfg = build_app_config_from_gui(settings, self.cwd)
        writer = QueueWriter(self.queue, "stdout")
        code = 1
        try:
            with redirect_stdout(writer), redirect_stderr(writer):
                code = run_convert(
                    cfg,
                    capture_session=self._capture_session_from_gui,
                    cancel_check=self._raise_if_cancelled,
                )
        except Exception:
            writer.flush()
            self.queue.put(("log", traceback.format_exc().rstrip()))
        finally:
            writer.flush()

        report = None
        produced = 0
        try:
            report = load_latest_report(cfg.paths.report_dir)
            produced = int(report.stats.get("converted", 0) or 0) + int(
                report.stats.get("partial", 0) or 0
            )
        except Exception as exc:
            self.queue.put(("log", f"無法讀取最近報告：{exc!r}"))

        now = current_timestamp()
        next_settings = replace(settings, last_run_at=now)
        if produced > 0:
            next_settings.last_markdown_output_at = now
        if report is not None:
            next_settings.last_report_path = str(report.path)
        save_gui_settings(next_settings, self.settings_path, self.cwd)

        if code == 130:
            summary = f"本輪已中止：exit={code}, 已產出/部分產出={produced}"
        else:
            summary = f"本輪完成：exit={code}, 新產出/部分產出={produced}"
        self.queue.put(("log", summary))
        self.queue.put(("settings", next_settings))
        return next_settings

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "next_run":
                    self.next_run_var.set(str(payload))
                elif kind == "settings":
                    self.settings = payload
                    self._refresh_last_run_labels()
                elif kind == "monitoring":
                    self.monitoring = bool(payload)
                    self._refresh_buttons()
                elif kind == "busy":
                    self.busy = bool(payload)
                    self._refresh_buttons()
                elif kind == "login_prompt":
                    self._handle_login_prompt(payload)
        except Empty:
            pass
        self.root.after(100, self._drain_queue)

    def _settings_from_ui(self) -> GuiSettings:
        input_dirs = [str(item) for item in self.input_list.get(0, self.tk.END)]
        if not input_dirs:
            raise ValueError("請至少新增一個輸入資料夾")
        interval = max(1, int(self.interval_var.get()))
        stable = max(0, int(self.stable_var.get()))
        return GuiSettings(
            config_path=self.config_path_var.get().strip() or None,
            input_dirs=input_dirs,
            output_dir=self.output_dir_var.get().strip(),
            work_dir=self.work_dir_var.get().strip(),
            report_dir=self.report_dir_var.get().strip(),
            public_fetch_mode=self.public_fetch_mode_var.get().strip() or "auto",
            interval_seconds=interval,
            stable_seconds=stable,
            fetch_urls=bool(self.fetch_urls_var.get()),
            enable_markitdown_plugins=bool(self.enable_markitdown_plugins_var.get()),
            enable_paddleocr=bool(self.enable_paddleocr_var.get()),
            paddle_profile=self.paddle_profile_var.get().strip() or "pp_ocr",
            enable_paddle_gpu=bool(self.enable_paddle_gpu_var.get()),
            paddle_device=self.paddle_device_var.get().strip() or "auto",
            enable_paddle_hpi=bool(self.enable_paddle_hpi_var.get()),
            image_llm_enabled=bool(self.image_llm_enabled_var.get()),
            image_llm_provider=self.image_llm_provider_var.get().strip() or "openai_compatible",
            image_llm_base_url=self.image_llm_base_url_var.get().strip(),
            image_llm_model=self.image_llm_model_var.get().strip(),
            image_llm_api_key_env=self.image_llm_api_key_env_var.get().strip(),
            image_llm_prompt=self.image_llm_prompt_var.get().strip(),
            skip_unchanged=bool(self.skip_unchanged_var.get()),
            overwrite=bool(self.overwrite_var.get()),
            enrich_filenames=bool(self.enrich_filenames_var.get()),
            start_monitor_on_launch=bool(self.launch_monitor_var.get()),
            autostart=bool(self.autostart_var.get()),
            last_run_at=self.settings.last_run_at,
            last_markdown_output_at=self.settings.last_markdown_output_at,
            last_report_path=self.settings.last_report_path,
        )

    def _sync_paddleocr_controls(self) -> None:
        if not hasattr(self, "paddle_profile_combo"):
            return
        state = "readonly" if self.enable_paddleocr_var.get() else "disabled"
        self.paddle_profile_combo.configure(state=state)
        gpu_state = (
            "readonly"
            if self.enable_paddleocr_var.get() and self.enable_paddle_gpu_var.get()
            else "disabled"
        )
        if hasattr(self, "paddle_device_combo"):
            self.paddle_device_combo.configure(state=gpu_state)

    def _apply_autostart(self) -> None:
        enabled = bool(self.autostart_var.get())
        if not enabled:
            if is_autostart_supported():
                set_autostart(False, self.settings_path)
            return
        if not is_autostart_supported():
            self._append_log("開機自啟目前只支援 Windows，已保留 GUI 設定但未寫入系統")
            return
        set_autostart(True, self.settings_path, start_monitor=True)

    def _refresh_last_run_labels(self) -> None:
        self.last_run_var.set(self.settings.last_run_at or "尚未執行")
        self.last_output_var.set(self.settings.last_markdown_output_at or "尚未產出")
        self.last_report_var.set(self.settings.last_report_path or "尚無報告")

    def _refresh_buttons(self) -> None:
        busy_state = self.tk.DISABLED if self.busy else self.tk.NORMAL
        monitor_state = self.tk.DISABLED if self.monitoring or self.busy else self.tk.NORMAL
        stop_state = self.tk.NORMAL if self.monitoring or self.busy else self.tk.DISABLED
        if hasattr(self, "run_button"):
            self.run_button.configure(state=busy_state)
            self.start_button.configure(state=monitor_state)
            self.stop_button.configure(state=stop_state)
            self.save_button.configure(state=busy_state)

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(self.tk.END, format_gui_log_line(line) + "\n")
        self.log_text.see(self.tk.END)
        self.log_text.configure(state="disabled")

    def _show_error(self, title: str, exc: Exception) -> None:
        from tkinter import messagebox

        self._append_log(f"{title}: {exc!r}")
        messagebox.showerror(title, str(exc))

    def _capture_session_from_gui(self, site, report) -> None:
        capture_session_state(site, report, confirm_login=self._wait_for_login_confirmation)

    def _wait_for_login_confirmation(self, site, report) -> None:
        request = LoginPromptRequest(site_name=site.name, done_event=Event())
        self.queue.put(("login_prompt", request))
        request.done_event.wait()
        if not request.confirmed:
            raise RuntimeError(f"{site.name}: login canceled from GUI")

    def _handle_login_prompt(self, request: LoginPromptRequest) -> None:
        from tkinter import messagebox

        self.status_var.set("等待登入確認")
        confirmed = messagebox.askokcancel(
            f"{request.site_name} 登入中",
            (
                f"已開啟 {request.site_name} 的登入瀏覽器。\n\n"
                "請先在瀏覽器完成登入，再回到這個視窗按「確定」儲存 session。\n"
                "若目前不想繼續，按「取消」。"
            ),
        )
        request.confirmed = bool(confirmed)
        request.done_event.set()
        if self.busy:
            self.status_var.set("執行轉換中")

    def _raise_if_cancelled(self) -> None:
        if self.stop_event.is_set():
            raise ConversionCancelled("GUI stop requested")


def current_timestamp() -> str:
    return _format_timestamp(datetime.now().astimezone())


_TIMESTAMPED_LOG_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?: [^\]]+)?\]")


def format_gui_log_line(line: str, *, now: datetime | None = None) -> str:
    text = line.rstrip()
    if _TIMESTAMPED_LOG_RE.match(text):
        return text
    timestamp = _format_timestamp(now or datetime.now().astimezone())
    return f"[{timestamp}] {text}"


def _format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S %Z")


def _open_path(path: Path) -> None:
    resolved = path.resolve()
    if sys.platform == "win32":
        os.startfile(str(resolved))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        import subprocess

        subprocess.Popen(["open", str(resolved)])
        return
    import subprocess

    subprocess.Popen(["xdg-open", str(resolved)])


def main(argv: list[str] | None = None) -> int:
    load_default_env()
    parser = argparse.ArgumentParser(prog="lmit-gui")
    parser.add_argument("--settings", type=Path, help="GUI settings JSON path")
    parser.add_argument(
        "--start-monitor",
        action="store_true",
        help="start folder monitoring after the window opens",
    )
    args = parser.parse_args(argv)

    try:
        import tkinter as tk
    except Exception as exc:
        print(f"Unable to start GUI because tkinter is unavailable: {exc}", file=sys.stderr)
        return 1

    settings_path = resolve_settings_path(args.settings, Path.cwd())
    root = tk.Tk()
    RawMarkdownGui(root, settings_path=settings_path, start_monitor=args.start_monitor)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
