# Part 1 Plan: Local Raw Markdown Ingestion

## Positioning

This project is the local desktop ingestion layer of LMIT.

Its job is to watch one or more folders, convert supported files and collected links into raw Markdown, and keep the original input folders read-only. The generated Markdown is intended to be the durable source layer for later knowledge-base workflows.

This is the only part planned for the first GitHub repository.

## Goals

- Provide a safe local pipeline for files and `.txt` URL collections.
- Support multiple input folders.
- Preserve input relative paths in output.
- Fetch link content by default.
- Support logged-in page capture through reusable browser sessions.
- Produce named raw Markdown files.
- Maintain a manifest so unchanged files are skipped.
- Produce readable conversion reports.
- Provide both CLI and GUI workflows for day-to-day use.
- Keep generated data, sessions, and private configs out of git.

## Non-Goals

- Building or maintaining an LLM wiki.
- Running a wiki-only Docker image.
- Reorganizing raw Markdown into topic/entity pages.
- Hosting a knowledge-base search or ask UI.
- Replacing source files or modifying input folders.

Those belong to Part 2 and should become a separate project.

## Current Architecture

```text
Input folders
  -> scanner
  -> manifest / unchanged filter
  -> local file converter
  -> txt URL extractor
  -> public URL fetcher
  -> session URL fetcher
  -> filename enrichment
  -> output/raw
  -> output/reports
```

Key modules:

- `src/lmit/cli.py`: CLI commands for convert, watch, login, report, and GUI launch.
- `src/lmit/gui.py`: Tkinter GUI for first-part ingestion.
- `src/lmit/gui_settings.py`: GUI settings load/save and AppConfig mapping.
- `src/lmit/autostart.py`: Windows startup registration.
- `src/lmit/config.py`: TOML config and defaults.
- `src/lmit/scanner.py`: input scanning, multiple roots, exclusions, stable-file delay.
- `src/lmit/pipeline.py`: conversion orchestration.
- `src/lmit/manifest.py`: persistent processing state.
- `src/lmit/reports.py`: report writing and diagnostics.
- `src/lmit/converters/`: local file and `.txt` URL conversion.
- `src/lmit/fetchers/`: public and session URL fetching.
- `src/lmit/sessions/`: browser session handling.

## GUI Requirements

The GUI should support:

- Selecting multiple input folders.
- Selecting output, work, and report folders.
- Configuring polling interval in seconds.
- Configuring stable-file delay in seconds.
- Showing last run date/time.
- Showing the last run date/time that produced Markdown.
- Starting and stopping folder monitoring.
- Running one conversion immediately.
- Opening the output folder.
- Opening the latest report.
- Enabling/disabling URL content fetching.
- Enabling/disabling skip unchanged.
- Enabling/disabling overwrite.
- Enabling/disabling filename enrichment.
- Enabling/disabling Windows startup monitoring.

Current implementation covers this baseline.

## CLI Requirements

Supported commands:

- `convert`: run one conversion.
- `watch`: poll folders and convert changes.
- `login`: create or refresh browser session state.
- `report`: inspect the latest or a specific conversion report.
- `gui`: open the GUI.

The CLI remains the stable automation interface; the GUI is a convenience layer over the same config and pipeline.

## Safety Rules

- Never write to input folders.
- Never delete source files.
- Never move or rename source files.
- Resolve output paths and verify they stay inside configured output directories.
- Keep temporary files under `work_dir`.
- Keep session state under `session_dir`.
- Treat session state and local GUI settings as private data.

## Release Checklist

- README describes only Part 1 usage.
- `docs/part1/plan.md` describes this public repository scope.
- Private requirement and second-part planning notes are not tracked in the public repository.
- `.gitignore` excludes generated data and private settings.
- `run.bat` starts the GUI from the project root.
- Tests pass with `python -m pytest`.
- GitHub remote is configured before push.

## Near-Term Improvements

- Add a packaged Windows shortcut or installer script.
- Add clearer GUI error states for missing optional dependencies.
- Add a sample local config template separate from `config.example.toml`.
- Add public URL fetcher tests with a local HTTP server.
- Add optional raw Markdown frontmatter for stronger traceability.
