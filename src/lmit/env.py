from __future__ import annotations

from pathlib import Path
import os


def load_default_env(cwd: Path | None = None) -> list[Path]:
    base = (cwd or Path.cwd()).resolve()
    loaded: list[Path] = []
    preexisting_keys = set(os.environ)
    loaded_keys: set[str] = set()
    for name in (".env", ".env.local"):
        path = base / name
        if not path.exists() or not path.is_file():
            continue
        _load_env_file(path, preexisting_keys=preexisting_keys, loaded_keys=loaded_keys)
        loaded.append(path)
    return loaded


def _load_env_file(path: Path, *, preexisting_keys: set[str], loaded_keys: set[str]) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_name = key.strip()
        if not env_name:
            continue
        if env_name in preexisting_keys and env_name not in loaded_keys:
            continue
        os.environ[env_name] = _parse_env_value(value)
        loaded_keys.add(env_name)


def _parse_env_value(raw_value: str) -> str:
    text = raw_value.strip()
    if not text:
        return ""
    if text[0] in {'"', "'"}:
        quote = text[0]
        end_index = _find_closing_quote(text, quote)
        if end_index == -1:
            inner = text[1:]
        else:
            inner = text[1:end_index]
        return _unescape_quoted(inner, quote)

    hash_index = text.find("#")
    if hash_index != -1:
        text = text[:hash_index].rstrip()
    return text


def _find_closing_quote(text: str, quote: str) -> int:
    escaped = False
    for index in range(1, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char == quote:
            return index
    return -1


def _unescape_quoted(text: str, quote: str) -> str:
    if quote == "'":
        return text
    return (
        text.replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )
