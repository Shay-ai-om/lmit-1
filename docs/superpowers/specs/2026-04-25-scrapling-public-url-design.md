# Scrapling Public URL Pipeline Design

## Summary

Integrate Scrapling into the public URL ingestion path to improve fetch success rate and reduce noisy page chrome, while leaving all logged-in site handling unchanged. The new path applies only when `SessionManager.site_for_url(url)` returns `None`.

The first release is intentionally conservative:

- Keep `SessionUrlFetcher` and all social-login/session code unchanged.
- Keep the existing MarkItDown and Playwright public fallback path available as a legacy safety net.
- Add a new public URL pipeline that prefers Scrapling for public pages and downgrades to legacy fetchers when Scrapling results are blank, blocked, too short, or error out.

## Goals

- Increase successful extraction for public URLs found in `.txt` sources.
- Reduce ad, navigation, footer, and unrelated page noise in public URL content.
- Preserve the current behavior for Facebook, Reddit, YouTube, X/Twitter, and any other configured session site.
- Make provider choice and fallback reasons visible in reports and in the running report written during batch execution.

## Non-Goals

- Do not replace or rework `SessionUrlFetcher`.
- Do not change the login/session bootstrap flow in `src/lmit/sessions/login.py`.
- Do not introduce site-specific extraction rules in the first Scrapling slice.
- Do not add GUI controls in the first slice; v1 is TOML-driven.

## Current State

Today, public URL handling in [src/lmit/fetchers/public_url.py](C:/codex_projext/lmit/src/lmit/fetchers/public_url.py) works like this:

1. Special-case npm package URLs.
2. Try `MarkItDownAdapter.convert_url(url)`.
3. If that fails and `work_dir` is available, render the page via Playwright, save HTML, then convert that HTML with MarkItDown.

This works but has two limits:

- Public URL success depends heavily on MarkItDown and a simple Playwright fallback.
- Public page extraction often includes noisy chrome because the system lacks a public-page-first cleanup pipeline.

## Proposed Architecture

### Boundary

The public URL path gains a new provider pipeline. Session URLs continue to use the existing split:

- Public URLs: `PublicUrlFetcher`
- Session URLs: `SessionUrlFetcher`

This keeps the current working session/login architecture isolated from the new experiment.

### New Components

1. `PublicFetchConfig` in [src/lmit/config.py](C:/codex_projext/lmit/src/lmit/config.py)
2. `ScraplingPublicFetcher` in `src/lmit/fetchers/public_url_scrapling.py`
3. Lightweight content-quality helpers in `src/lmit/fetchers/public_url_quality.py`
4. Expanded orchestration in [src/lmit/fetchers/public_url.py](C:/codex_projext/lmit/src/lmit/fetchers/public_url.py)

### Provider Model

The new public pipeline introduces four logical provider stages:

1. `scrapling_static`
2. `scrapling_dynamic`
3. `legacy_markitdown_url`
4. `legacy_playwright_html`

The pipeline remains synchronous and returns plain markdown text to the caller, matching the current `PublicUrlFetcher.fetch(url) -> str` contract.

## Fallback Order

The new fallback order applies only to public URLs.

### Stage 1: Scrapling Static

Use Scrapling's lightweight HTTP fetch path first, configured with:

- timeout
- browser impersonation / stealthy headers where available
- optional `ai-targeted` cleanup
- optional CSS selector support reserved for future config, not enabled in v1

If the result is:

- non-empty
- not obviously blocked
- and above the configured meaningful-character threshold

then accept it immediately.

### Stage 2: Scrapling Dynamic

If static fetch returns an exception, blocked content, blank content, or low-quality content, upgrade to Scrapling's dynamic/browser-backed fetch path.

Dynamic is used only when enabled in config. It is not the default for every public URL.

### Stage 3: Legacy MarkItDown URL

If Scrapling dynamic is disabled or fails, fall back to the current MarkItDown URL fetch path.

### Stage 4: Legacy Playwright HTML

If MarkItDown URL fetch fails, fall back to the existing Playwright-rendered HTML path and then convert that saved HTML with MarkItDown.

## Quality Gate Rules

The first version should use simple, explainable rules rather than a scoring system.

Treat a result as unacceptable when any of the following is true:

- the fetch raised an exception
- the extracted text is blank after trimming
- the content matches the existing blocked/login/bot-check markers
- the number of meaningful characters is below `min_meaningful_chars`

Meaningful-character counting should:

- strip whitespace
- ignore repeated blank lines
- count visible text only

The quality gate is deliberately simple so report logs remain understandable.

## Configuration

Add a new `[public_fetch]` block to TOML and to the config model.

### Proposed TOML

```toml
[public_fetch]
provider = "auto"
enable_scrapling = true
enable_scrapling_dynamic = true
scrapling_cleanup = "ai_targeted"
scrapling_block_ads = true
request_timeout_seconds = 30
navigation_timeout_ms = 45000
min_meaningful_chars = 200
```

### Field Semantics

- `provider`
  - `auto`: use the new mixed public pipeline
  - `legacy`: preserve the current MarkItDown-first path

- `enable_scrapling`
  - master switch for Scrapling on public URLs

- `enable_scrapling_dynamic`
  - permit escalation from static to browser-backed Scrapling

- `scrapling_cleanup`
  - `none`: no cleanup beyond what the fetcher naturally returns
  - `basic`: minimal text cleanup
  - `ai_targeted`: use Scrapling's AI-oriented main-content/noise stripping mode

- `scrapling_block_ads`
  - enable Scrapling's ad/resource blocking features when supported by the chosen fetcher

- `request_timeout_seconds`
  - timeout for HTTP/static public fetches

- `navigation_timeout_ms`
  - timeout for browser/dynamic public fetches

- `min_meaningful_chars`
  - minimum visible-character threshold before escalating to the next provider

## Reporting Changes

### New Stats

Add the following counters to `ConversionStats` in [src/lmit/reports.py](C:/codex_projext/lmit/src/lmit/reports.py):

- `public_url_scrapling_static_success`
- `public_url_scrapling_dynamic_success`
- `public_url_markitdown_success`
- `public_url_playwright_success`
- `public_url_quality_retry`
- `public_url_blocked`
- `public_url_blank`

These are in addition to the existing `url_fetch_success` / `url_fetch_failed` totals.

### New Log Lines

Add structured log lines that make the pipeline explain itself:

- `[URL-FETCH-PROVIDER] provider=scrapling_static url=...`
- `[URL-FETCH-UPGRADE] from=scrapling_static to=scrapling_dynamic reason=too_short`
- `[URL-FETCH-UPGRADE] from=scrapling_dynamic to=legacy_markitdown_url reason=blocked`
- `[URL-FETCH-QUALITY] provider=scrapling_static chars=153 blocked=false blank=false`
- `[URL-FETCH-DONE] provider=scrapling_dynamic url=...`

These lines should appear in both the final report and the running report.

## Dependency Strategy

Add Scrapling as an optional dependency, not a required base dependency.

Recommended extras:

```toml
[project.optional-dependencies]
scrapling = [
  "scrapling[fetchers]>=0.4,<0.5",
]
```

The base install remains lightweight. Users who want improved public URL fetching explicitly install the extra.

The README should document any additional setup required by Scrapling, including its browser/runtime install step if needed.

## File Changes

### Create

- `src/lmit/fetchers/public_url_scrapling.py`
- `src/lmit/fetchers/public_url_quality.py`
- `tests/test_public_url_quality.py`
- `tests/test_public_url_pipeline.py`

### Modify

- [src/lmit/config.py](C:/codex_projext/lmit/src/lmit/config.py)
- [src/lmit/fetchers/public_url.py](C:/codex_projext/lmit/src/lmit/fetchers/public_url.py)
- [src/lmit/reports.py](C:/codex_projext/lmit/src/lmit/reports.py)
- [pyproject.toml](C:/codex_projext/lmit/pyproject.toml)
- [config/config.example.toml](C:/codex_projext/lmit/config/config.example.toml)
- [README.md](C:/codex_projext/lmit/README.md)

## Error Handling

- If Scrapling is not installed and `provider = "auto"`, log that Scrapling is unavailable and continue via legacy providers.
- If Scrapling static fails, log the reason and escalate.
- If Scrapling dynamic fails, log the reason and escalate.
- If all providers fail, preserve the current behavior: surface a fetch failure in the markdown output and increment failure stats.

No provider error should block the whole batch. Failures remain per-URL.

## Verification Strategy

### Automated

1. Config loading tests
   - defaults
   - TOML overrides
   - `provider=legacy` bypassing Scrapling

2. Quality-rule tests
   - blank detection
   - blocked detection
   - low-character escalation

3. Pipeline tests
   - static success without escalation
   - static blank -> dynamic success
   - dynamic blocked -> legacy success
   - session sites bypassing Scrapling

4. Report tests
   - new stats are recorded
   - log lines are rendered
   - running report includes provider/upgrade lines

### Manual

Run a curated batch of public URLs covering:

- simple article pages
- JS-heavy public pages
- mildly protected public pages
- noisy marketing/news pages

Compare before/after on:

- fetch success rate
- timeout behavior
- output length
- visible ad/chrome noise
- incidence of login/bot-check pages being mistaken for real content

## Rollout

The feature should ship behind TOML config with `provider = "auto"` in the example config and a documented fallback to `provider = "legacy"` for troubleshooting.

This gives users an immediate escape hatch if a site behaves worse with Scrapling.

## Open Decisions Resolved For v1

- Public URLs only: yes
- Session sites touched: no
- GUI controls in v1: no
- Simple rule-based quality gate: yes
- Optional dependency instead of required base dependency: yes

## References

- [Scrapling GitHub](https://github.com/D4Vinci/Scrapling)
- [Fetchers API](https://scrapling.readthedocs.io/en/latest/api-reference/fetchers.html)
- [Stealthy fetching](https://scrapling.readthedocs.io/en/latest/fetching/stealthy.html)
- [Extract command and AI-targeted mode](https://scrapling.readthedocs.io/en/latest/cli/extract-commands.html)
