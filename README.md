# LMIT Raw Markdown Ingestion

LMIT is a local desktop tool for turning files and collected links into raw Markdown.
This repository currently publishes only the first part of the project: local raw Markdown ingestion.

The planned wiki-only knowledge-base layer is not part of this GitHub release. It will be split into a separate project later.

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

The exact conversion quality depends on the installed MarkItDown extras. The base install is intentionally lightweight.

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

For a dry run that preserves links but does not fetch page content:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml --no-fetch-urls
```

When a `.txt` file contains URLs, LMIT writes a Markdown note containing the original text, the detected link list, fetched page content, and any fetch errors.

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
```

## Safety Notes

- Input folders are treated as read-only.
- Generated output, reports, manifests, session files, and GUI settings should stay out of git.
- Session files may contain sensitive cookies.
- Use `config/config.example.toml` as the public template and keep private configs local.

## Development

Run tests:

```powershell
.\.venv\Scripts\python -m pytest
```

Project planning:

- [docs/part1/plan.md](docs/part1/plan.md): current raw Markdown ingestion project

Private requirement and second-part planning notes are intentionally kept out of the public repository.
