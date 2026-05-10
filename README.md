# LMIT Raw Markdown Ingestion

LMIT is a local desktop tool for turning files and collected links into raw Markdown.
This repository currently publishes only the first part of the project: local raw Markdown ingestion.

The planned wiki-only knowledge-base layer is tracked separately in [docs/part2/plan.md](docs/part2/plan.md) and is not part of this GitHub release.

LMIT uses [Microsoft MarkItDown](https://github.com/microsoft/markitdown) as its core document-to-Markdown converter, with optional extras for broader document support.

## What It Does

- Reads one or more input folders.
- Recursively converts supported files into Markdown.
- Extracts URLs from `.txt` files and fetches link content when enabled.
- Supports logged-in page capture through saved browser sessions, currently with Facebook defaults.
- Writes raw Markdown to `output/raw/`.
- Writes conversion reports to `output/reports/`.
- Keeps manifests and temporary files in `.lmit_work/`.
- Never writes into, moves, renames, or deletes files from the input folders.
- Provides both CLI commands and a Windows-friendly GUI.

## Supported Inputs

Default supported extensions:

```text
.md, .markdown, .txt, .pdf, .docx, .pptx, .xlsx, .xls,
.html, .htm, .csv, .json, .xml, .jpg, .jpeg, .png
```

The exact conversion quality depends on the installed [Microsoft MarkItDown](https://github.com/microsoft/markitdown) extras. The base install is intentionally lightweight.

For image-to-Markdown work, there are two separate pieces:

- OCR depends on MarkItDown plugins being installed and enabled.
- Image description depends on a configured multimodal LLM provider.
- For scanned PDFs and embedded document images, install the optional `markitdown-ocr` plugin. LMIT can pass the same configured `llm_client` / `llm_model` path through to that plugin.

## Install

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

For broader document support:

```powershell
.\.venv\Scripts\python -m pip install -e ".[documents,dev]"
```

For the full MarkItDown optional set:

```powershell
.\.venv\Scripts\python -m pip install -e ".[full,dev]"
```

The `full` extra now also installs the optional `markitdown-ocr` plugin.

If you want the OCR plugin without the rest of the full MarkItDown extras:

```powershell
.\.venv\Scripts\python -m pip install -e ".[ocr,dev]"
```

If you want image descriptions through MarkItDown, set an API key environment variable before running LMIT when your provider needs one. Example for OpenAI:

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

LMIT automatically loads `.env` and then `.env.local` from the current working directory at startup. Values already present in the process environment are kept as-is.

Sample config files you can copy from:

- `config/config.example.toml` - full project config
- `config/markitdown-llm.sample.toml` - minimal MarkItDown LLM sample
- `.env.sample` - sample environment variable file

For the Scrapling public-URL pipeline:

```powershell
.\.venv\Scripts\python -m pip install -e ".[scrapling,dev]"
.\.venv\Scripts\scrapling install
```

If you skip the Scrapling extra, public URLs still work. The new pipeline will fall back to the legacy MarkItDown path when Scrapling is unavailable.

For logged-in page capture:

```powershell
.\.venv\Scripts\python -m pip install -e ".[session]"
.\.venv\Scripts\python -m playwright install chromium
```

## GUI Usage

Start the GUI with:

```powershell
.\run.bat
```

or:

```powershell
.\.venv\Scripts\python -m lmit.gui
```

The GUI can configure:

- multiple input folders
- output raw Markdown folder
- work folder
- report folder
- input folder polling frequency in seconds
- file stable time before processing
- URL content fetching
- skip unchanged files
- overwrite behavior
- filename enrichment
- last run time
- last run time that actually produced Markdown
- latest report path
- Windows startup monitoring

GUI settings are saved in `config/gui.settings.json`, which should stay local and is ignored by git.

## CLI Usage

Run one conversion:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml
```

Use multiple input folders:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml --input input --input input_extra
```

When multiple input roots are configured, output files are namespaced by input folder label to avoid collisions. For example:

```text
output/raw/input/note.md
output/raw/input_extra/note.md
```

Monitor folders continuously:

```powershell
.\.venv\Scripts\python -m lmit.cli watch --config config/config.example.toml
```

`watch` scans every `polling.interval_seconds` seconds. In watch and GUI monitoring mode, files newer than `polling.stable_seconds` are skipped until a later scan, which helps avoid processing files while Nextcloud or another sync tool is still writing them.

Inspect the latest report:

```powershell
.\.venv\Scripts\python -m lmit.cli report --config config/config.example.toml
.\.venv\Scripts\python -m lmit.cli report --config config/config.example.toml --summary
.\.venv\Scripts\python -m lmit.cli report --config config/config.example.toml --failed
.\.venv\Scripts\python -m lmit.cli report --config config/config.example.toml --json
```

Retry one file:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml --only "AI/20260413_072753.txt" --overwrite
```

Retry only failed or retryable partial records:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml --retry-failed --overwrite
```

## URL Fetching

Normal ingestion should keep URL fetching enabled:

```toml
[conversion]
fetch_urls = true
```

Public URLs use the new Scrapling-first pipeline when `provider = "auto"`. Session-backed sites do not use this block; they continue through the logged-in session pipeline.

If Scrapling is not installed, that public pipeline falls back automatically to the legacy MarkItDown provider.

For JS-heavy or Cloudflare-like public pages, you can enable Scrapling's
StealthyFetcher as a later fallback. It is disabled by default because it can
open a stealth browser and wait longer for challenge pages:

```toml
[public_fetch]
provider = "auto"
enable_scrapling = true
enable_scrapling_dynamic = true
enable_scrapling_stealthy = true
scrapling_stealthy_solve_cloudflare = true
```

If you only want that higher-cost path for Cloudflare challenge pages, leave
general stealth mode off and keep Cloudflare auto-detection on:

```toml
[public_fetch]
provider = "auto"
enable_scrapling = true
enable_scrapling_dynamic = true
enable_scrapling_stealthy = false
enable_scrapling_stealthy_on_cloudflare = true
scrapling_stealthy_solve_cloudflare = true
```

To roll public URLs back to the older MarkItDown-first flow, set:

```toml
[public_fetch]
provider = "legacy"
```

For some public sites that behave differently in a real browser than in automated fetchers, you can tell the final browser fallback to attach to a real browser session over Chrome DevTools Protocol:

```toml
[public_fetch]
provider = "auto"
browser_connect_over_cdp = true
browser_cdp_port = 9225
```

Then start Chrome or Edge yourself with remote debugging enabled before running conversion. Example for Chrome on Windows:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9225 `
  --user-data-dir="$env:TEMP\lmit-public-browser"
```

Open the target page in that browser once, confirm it loads normally, then run LMIT. When `browser_connect_over_cdp = true`, the public-URL browser fallback reuses that real browser context instead of launching a fresh Playwright browser.

For domains that should use that already-open browser before Scrapling or
MarkItDown, add `cdp_first_domains`. Parent domains match subdomains, so
`baidu.com` also covers `tieba.baidu.com`. LMIT can launch that CDP browser
itself with a persistent profile, so you do not need to start remote debugging
by hand. The default config enables this for Baidu/Tieba:

```toml
[public_fetch]
provider = "auto"
public_browser_auto_launch = true
public_browser_profile_dir = ".lmit_work/browser_profiles/public"
public_browser_verification_timeout_seconds = 180
public_browser_verification_poll_seconds = 3
cdp_first_domains = ["baidu.com"]
```

When the browser opens for a challenged site, complete the verification in that
window once. If the page still looks like a security check after navigation,
LMIT waits and polls the same browser tab until the verification clears or the
configured timeout expires. Later runs reuse the same profile and cookies.

For a dry run that preserves links but does not fetch page content:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml --no-fetch-urls
```

When a `.txt` file contains URLs, LMIT writes a Markdown note containing the original text, the detected link list, fetched page content, and any fetch errors.

## MarkItDown LLM

LMIT now exposes MarkItDown image-description settings through both TOML and the GUI.

If you want a minimal starting point instead of the full project config, start from `config/markitdown-llm.sample.toml` and pair it with `.env.sample`.

Example TOML:

```toml
[conversion]
enable_markitdown_plugins = true

[markitdown]
llm_enabled = true
llm_provider = "openai_compatible"
llm_base_url = ""
llm_model = "gpt-4.1-mini"
llm_api_key_env = "OPENAI_API_KEY"
llm_prompt = "Write a detailed caption for this image."
```

Notes:

- `enable_markitdown_plugins = true` is still the switch that allows OCR plugins to load.
- `llm_enabled = true` enables image captioning for `.jpg`, `.jpeg`, and `.png`.
- `markitdown[all]` by itself does not install third-party plugins. In LMIT, install `.[ocr,dev]` or `.[full,dev]` if you want the optional `markitdown-ocr` plugin for scanned PDFs and embedded Office images.
- When plugins and the LLM provider are enabled, LMIT logs `[MARKITDOWN-PLUGINS] ...` at startup. If OCR is still unavailable, it also logs `[MARKITDOWN-OCR-MISSING] ...`.
- Supported providers are:
  - `openai_compatible`
  - `gemini`
  - `lm_studio`
  - `ollama`
- `llm_api_key_env` names the environment variable that stores the API key. The key itself is not stored in the TOML or GUI settings file.
- LMIT automatically loads `.env` and `.env.local` from the working directory before CLI and GUI startup.
- `llm_base_url` can be left blank to use the provider default:
  - `openai_compatible` -> `https://api.openai.com/v1`
  - `gemini` -> `https://generativelanguage.googleapis.com/v1beta`
  - `lm_studio` -> `http://127.0.0.1:1234/v1`
  - `ollama` -> `http://127.0.0.1:11434/api`
- `gemini` uses the native Gemini `generateContent` API.
- `lm_studio` uses LM Studio's OpenAI-compatible `/v1/chat/completions` endpoint.
- `ollama` uses Ollama's native `/api/chat` endpoint.
- For local providers, `llm_api_key_env` can be blank.

Provider quick reference:

```text
openai_compatible
  base URL: https://api.openai.com/v1

gemini
  base URL: https://generativelanguage.googleapis.com/v1beta
  runtime endpoint shape: /models/<model>:generateContent

lm_studio
  base URL: http://127.0.0.1:1234/v1
  default local port: 1234
  runtime endpoint shape: /chat/completions

ollama
  base URL: http://127.0.0.1:11434/api
  default local port: 11434
  runtime endpoint shape: /chat
```

If `llm_enabled = true` but `llm_model` is blank, or a remote provider such as `openai_compatible` / `gemini` is missing its configured API key environment variable, LMIT will raise a configuration error at startup instead of silently producing blank image output.

## Logged-In Pages

Install the session extras first:

```powershell
.\.venv\Scripts\python -m pip install -e ".[session]"
.\.venv\Scripts\python -m playwright install chromium
```

Create or refresh a Facebook session:

```powershell
.\.venv\Scripts\python -m lmit.cli login --site facebook --config config/config.example.toml
```

The example config also includes generic session entries for Reddit, YouTube, and X/Twitter. To sign in manually before running GUI or batch conversion:

```powershell
.\.venv\Scripts\python -m lmit.cli login --site reddit --config config/config.example.toml
.\.venv\Scripts\python -m lmit.cli login --site youtube --config config/config.example.toml
.\.venv\Scripts\python -m lmit.cli login --site x --config config/config.example.toml
```

Session state is saved under:

```text
sessions/facebook_state.json
sessions/reddit_state.json
sessions/youtube_state.json
sessions/x_state.json
```

The social-site examples are configured to avoid the default fresh Playwright Chromium login context:

- `reddit`: persistent Microsoft Edge profile
- `youtube`: persistent Google Chrome profile
- `x`: persistent Microsoft Edge profile

They also enable `login_connect_over_cdp`, which means LMIT launches the real browser executable first and then attaches to it over Chrome DevTools Protocol, instead of asking Playwright to launch the login window directly. Conversion uses the same CDP profile for those session sites, so Reddit, YouTube, and X can reuse the real browser cookies/profile during fetches rather than falling back to a fresh Playwright browser.

This helps with repeated bot-challenge loops on sites that dislike the default Playwright browser fingerprint. If you want to change browser channel, edit the matching session block. For example:

```toml
browser_channel = "msedge"
```

to:

```toml
browser_channel = "chrome"
```

The persistent profiles are stored under:

```text
.lmit_work/browser_profiles/reddit
.lmit_work/browser_profiles/youtube
.lmit_work/browser_profiles/x
```

The default CDP ports in the example config are:

```text
reddit   9222
youtube  9223
x        9224
```

If your browser is installed in a non-standard location, add `browser_executable_path` to that session block.

Then run conversion as usual:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml
```

If a configured logged-in site needs a session and the session is missing or expired, LMIT opens a visible browser window and logs `[LOGIN-REQUIRED]`.

Facebook has a site-specific strategy. Reddit, YouTube, and X/Twitter currently use the generic session flow, so login state reuse is supported, but complex page behavior such as dynamic expansion, comments, video metadata, captions, anti-bot prompts, or two-factor verification may still require manual handling or future site-specific strategies.

## Output Naming

Enable filename enrichment in TOML:

```toml
[output_naming]
enrich_filenames = true
prefix_source = "auto"
max_prefix_chars = 64
separator = "__"
```

This prefixes the output Markdown filename with the first useful heading or content line. Source files are not renamed.

You can also enable it per run:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml --enrich-filenames
```

## Important Paths

```text
input/              local example input folder; do not commit personal data
output/raw/         generated raw Markdown
output/reports/     conversion reports
.lmit_work/         manifest and temporary files
sessions/           browser session state
config/             example and local configuration
docs/part1/plan.md  first-part plan
docs/part2/plan.md  second-part plan
```

## Safety Notes

- Input folders are treated as read-only.
- Generated output, reports, manifests, session files, and GUI settings should stay out of git.
- Session files may contain sensitive cookies.
- Use `config/config.example.toml` as the public template and keep private configs local.
- The wiki-related sections in `config/config.example.toml` are reserved placeholders for the future split-out wiki project.

## Development

Run tests:

```powershell
.\.venv\Scripts\python -m pytest
```

Project planning:

- [docs/part1/plan.md](docs/part1/plan.md): current raw Markdown ingestion project
- [docs/part2/plan.md](docs/part2/plan.md): future wiki-only knowledge-base project
