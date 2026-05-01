# LMIT Clean Install Checklist

This checklist is for a clean Windows install of the current `codex/markdown-gui` branch.

## 1. Clone the repository

```powershell
git clone https://github.com/Shay-ai-om/lmit-1.git
cd lmit-1
git fetch origin
git switch --track origin/codex/markdown-gui
```

## 2. Create a fresh virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
```

## 3. Install Python dependencies

Recommended full install:

```powershell
.\.venv\Scripts\python -m pip install -e ".[full,scrapling,session,dev]"
```

This includes:

- Microsoft MarkItDown full extras
- Scrapling
- session/login support
- test/dev dependencies

## 4. Install browser dependencies

```powershell
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\scrapling install
```

## 5. Prepare local config files

Copy the sample files:

```powershell
Copy-Item config\config.example.toml config\config.local.toml
Copy-Item .env.sample .env.local
```

Useful sample files:

- `config/config.example.toml` -> full project config
- `config/markitdown-llm.sample.toml` -> minimal MarkItDown LLM config
- `.env.sample` -> sample environment variable file

## 6. Edit your config

Main config:

- `config/config.local.toml`

Typical things to set:

- input folders
- output folder
- report folder
- public URL mode
- MarkItDown image LLM provider/model

## 7. Set environment variables

LMIT automatically loads `.env` and `.env.local` from the project root when CLI or GUI starts.

Recommended:

```powershell
Copy-Item .env.sample .env.local
```

Then edit `.env.local`.

Example for OpenAI:

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

Example for Gemini:

```powershell
$env:GEMINI_API_KEY = "..."
```

If you prefer, you can still set them directly in your shell. Existing environment variables win over values from `.env` files.

## 8. Provider reference

### OpenAI-compatible

- provider: `openai_compatible`
- default base URL: `https://api.openai.com/v1`
- API key usually required

### Gemini

- provider: `gemini`
- default base URL: `https://generativelanguage.googleapis.com/v1beta`
- runtime endpoint: `/models/<model>:generateContent`
- API key required

### LM Studio

- provider: `lm_studio`
- default base URL: `http://127.0.0.1:1234/v1`
- default local port: `1234`
- API key usually not required

### Ollama

- provider: `ollama`
- default base URL: `http://127.0.0.1:11434/api`
- default local port: `11434`
- API key usually not required

## 9. Example MarkItDown image LLM config

### Gemini

```toml
[conversion]
enable_markitdown_plugins = true

[markitdown]
llm_enabled = true
llm_provider = "gemini"
llm_base_url = ""
llm_model = "gemini-2.5-flash"
llm_api_key_env = "GEMINI_API_KEY"
llm_prompt = "Write a detailed caption for this image."
```

### Ollama

```toml
[conversion]
enable_markitdown_plugins = true

[markitdown]
llm_enabled = true
llm_provider = "ollama"
llm_base_url = ""
llm_model = "gemma3:4b"
llm_api_key_env = ""
llm_prompt = "Write a detailed caption for this image."
```

## 10. Start the GUI

```powershell
.\run.bat
```

or:

```powershell
.\.venv\Scripts\python -m lmit.gui
```

## 11. GUI checks before first run

Confirm these in the GUI:

- base TOML points to `config/config.local.toml`
- input/output/report paths are correct
- `Public URL mode` is set as intended
- `Enable MarkItDown plugins` is enabled if you want OCR plugins
- `Image LLM` is enabled if you want image captioning
- `LLM provider` is correct
- `LLM model` is filled in
- `API key env var` matches your chosen provider, or is blank for local providers

## 12. Optional: first smoke test

Run a small conversion first before pointing at a large folder:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config\config.local.toml --overwrite
```

Or test only a small image folder through the GUI.

## 13. If using login-required sites

Install session dependencies first:

```powershell
.\.venv\Scripts\python -m pip install -e ".[session]"
.\.venv\Scripts\python -m playwright install chromium
```

Then create login sessions as needed:

```powershell
.\.venv\Scripts\python -m lmit.cli login --site facebook --config config\config.local.toml
.\.venv\Scripts\python -m lmit.cli login --site reddit --config config\config.local.toml
.\.venv\Scripts\python -m lmit.cli login --site youtube --config config\config.local.toml
.\.venv\Scripts\python -m lmit.cli login --site x --config config\config.local.toml
```

## 14. Done

Once the small smoke test works, point the GUI or CLI at your real input folders.
