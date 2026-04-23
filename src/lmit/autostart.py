from __future__ import annotations

from pathlib import Path
import subprocess
import sys


RUN_VALUE_NAME = "LMIT Raw Markdown GUI"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_autostart_supported() -> bool:
    return sys.platform == "win32"


def build_autostart_command(
    settings_path: Path,
    *,
    executable: Path | None = None,
    start_monitor: bool = True,
) -> str:
    python_executable = executable or _windowed_python_executable(Path(sys.executable))
    args = [
        str(python_executable),
        "-m",
        "lmit.gui",
        "--settings",
        str(settings_path),
    ]
    if start_monitor:
        args.append("--start-monitor")
    return subprocess.list2cmdline(args)


def read_autostart_command() -> str | None:
    if not is_autostart_supported():
        return None

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def is_autostart_enabled() -> bool:
    return read_autostart_command() is not None


def set_autostart(
    enabled: bool,
    settings_path: Path,
    *,
    start_monitor: bool = True,
) -> None:
    if not is_autostart_supported():
        raise RuntimeError("開機自啟目前只支援 Windows")

    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        RUN_KEY_PATH,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            command = build_autostart_command(settings_path, start_monitor=start_monitor)
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass


def _windowed_python_executable(executable: Path) -> Path:
    if executable.name.lower() != "python.exe":
        return executable
    pythonw = executable.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else executable
