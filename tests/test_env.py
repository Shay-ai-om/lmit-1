from __future__ import annotations

import os
from pathlib import Path

from lmit.env import load_default_env


def test_load_default_env_reads_dotenv_files(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    (tmp_path / ".env").write_text(
        'OPENAI_API_KEY="root-key"\nSHARED_VALUE=from-dotenv\n',
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        'GEMINI_API_KEY=local-key\nSHARED_VALUE=from-local\n',
        encoding="utf-8",
    )

    loaded = load_default_env(tmp_path)

    assert loaded == [tmp_path / ".env", tmp_path / ".env.local"]
    assert os.environ["OPENAI_API_KEY"] == "root-key"
    assert os.environ["GEMINI_API_KEY"] == "local-key"
    assert os.environ["SHARED_VALUE"] == "from-local"


def test_load_default_env_preserves_preexisting_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "already-set")
    (tmp_path / ".env").write_text('OPENAI_API_KEY="from-dotenv"\n', encoding="utf-8")

    load_default_env(tmp_path)

    assert os.environ["OPENAI_API_KEY"] == "already-set"


def test_load_default_env_supports_export_and_inline_comments(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LMIT_SAMPLE", raising=False)
    monkeypatch.delenv("LMIT_NOTE", raising=False)
    (tmp_path / ".env").write_text(
        "export LMIT_SAMPLE=abc123 # keep this\n"
        'LMIT_NOTE="line1\\nline2"\n',
        encoding="utf-8",
    )

    load_default_env(tmp_path)

    assert os.environ["LMIT_SAMPLE"] == "abc123"
    assert os.environ["LMIT_NOTE"] == "line1\nline2"
