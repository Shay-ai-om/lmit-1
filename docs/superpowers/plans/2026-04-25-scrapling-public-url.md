# Scrapling Public URL Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Scrapling-first public URL fetch pipeline that improves success rate and content cleanliness for non-session URLs while preserving the current session/login behavior.

**Architecture:** Keep `SessionUrlFetcher` unchanged. Add a new config surface for public fetching, introduce Scrapling-backed static and dynamic public providers, and extend `PublicUrlFetcher` to orchestrate provider fallback plus reporting. Preserve the current MarkItDown and Playwright public path as legacy fallback.

**Tech Stack:** Python 3.11+, Scrapling, MarkItDown, Playwright, pytest, TOML config

---

## File Map

- Create: `src/lmit/fetchers/public_url_scrapling.py`
- Create: `src/lmit/fetchers/public_url_quality.py`
- Create: `tests/test_public_fetch_config.py`
- Create: `tests/test_public_url_quality.py`
- Create: `tests/test_public_url_pipeline.py`
- Modify: `src/lmit/config.py`
- Modify: `src/lmit/fetchers/public_url.py`
- Modify: `src/lmit/reports.py`
- Modify: `pyproject.toml`
- Modify: `config/config.example.toml`
- Modify: `README.md`

### Task 1: Add Public Fetch Config

**Files:**
- Create: `tests/test_public_fetch_config.py`
- Modify: `src/lmit/config.py`
- Modify: `config/config.example.toml`

- [ ] **Step 1: Write the failing config tests**

```python
from pathlib import Path

from lmit.config import default_config, load_config


def test_default_config_includes_public_fetch_block(tmp_path: Path):
    cfg = default_config(cwd=tmp_path)

    assert cfg.public_fetch.provider == "auto"
    assert cfg.public_fetch.enable_scrapling is True
    assert cfg.public_fetch.enable_scrapling_dynamic is True
    assert cfg.public_fetch.scrapling_cleanup == "ai_targeted"
    assert cfg.public_fetch.min_meaningful_chars == 200


def test_load_config_reads_public_fetch_overrides(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '''
[public_fetch]
provider = "legacy"
enable_scrapling = false
enable_scrapling_dynamic = false
scrapling_cleanup = "basic"
scrapling_block_ads = false
request_timeout_seconds = 12
navigation_timeout_ms = 12345
min_meaningful_chars = 80
''',
        encoding="utf-8",
    )

    cfg = load_config(config_path, cwd=tmp_path)

    assert cfg.public_fetch.provider == "legacy"
    assert cfg.public_fetch.enable_scrapling is False
    assert cfg.public_fetch.enable_scrapling_dynamic is False
    assert cfg.public_fetch.scrapling_cleanup == "basic"
    assert cfg.public_fetch.scrapling_block_ads is False
    assert cfg.public_fetch.request_timeout_seconds == 12
    assert cfg.public_fetch.navigation_timeout_ms == 12345
    assert cfg.public_fetch.min_meaningful_chars == 80
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_public_fetch_config.py -v`  
Expected: FAIL because `AppConfig` has no `public_fetch` attribute yet.

- [ ] **Step 3: Write minimal config implementation**

Add a new dataclass in `src/lmit/config.py`:

```python
@dataclass(frozen=True)
class PublicFetchConfig:
    provider: str = "auto"
    enable_scrapling: bool = True
    enable_scrapling_dynamic: bool = True
    scrapling_cleanup: str = "ai_targeted"
    scrapling_block_ads: bool = True
    request_timeout_seconds: int = 30
    navigation_timeout_ms: int = 45000
    min_meaningful_chars: int = 200
```

Wire it into `AppConfig`, `default_config()`, and `load_config()`:

```python
public_fetch_data = data.get("public_fetch", {})
public_fetch = PublicFetchConfig(
    provider=str(public_fetch_data.get("provider", "auto")).lower(),
    enable_scrapling=bool(public_fetch_data.get("enable_scrapling", True)),
    enable_scrapling_dynamic=bool(public_fetch_data.get("enable_scrapling_dynamic", True)),
    scrapling_cleanup=str(public_fetch_data.get("scrapling_cleanup", "ai_targeted")).lower(),
    scrapling_block_ads=bool(public_fetch_data.get("scrapling_block_ads", True)),
    request_timeout_seconds=int(public_fetch_data.get("request_timeout_seconds", 30)),
    navigation_timeout_ms=int(public_fetch_data.get("navigation_timeout_ms", 45000)),
    min_meaningful_chars=int(public_fetch_data.get("min_meaningful_chars", 200)),
)
```

Add the same block to `config/config.example.toml`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python -m pytest tests/test_public_fetch_config.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_public_fetch_config.py src/lmit/config.py config/config.example.toml
git commit -m "feat: add public fetch config"
```

### Task 2: Add Public URL Quality Helpers

**Files:**
- Create: `tests/test_public_url_quality.py`
- Create: `src/lmit/fetchers/public_url_quality.py`

- [ ] **Step 1: Write the failing quality tests**

```python
from lmit.fetchers.public_url_quality import quality_reason


def test_quality_reason_reports_blank():
    assert quality_reason("   ", min_meaningful_chars=200) == "blank"


def test_quality_reason_reports_too_short():
    assert quality_reason("short body", min_meaningful_chars=50) == "too_short"


def test_quality_reason_reports_blocked():
    text = "Just a moment... checking your browser before accessing the page"
    assert quality_reason(text, min_meaningful_chars=10) == "blocked"


def test_quality_reason_accepts_meaningful_text():
    text = "A" * 250
    assert quality_reason(text, min_meaningful_chars=200) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_public_url_quality.py -v`  
Expected: FAIL because the module does not exist yet.

- [ ] **Step 3: Write minimal quality implementation**

Create `src/lmit/fetchers/public_url_quality.py` with:

```python
from __future__ import annotations

import re

from lmit.converters.txt_urls import _blocked_content


def meaningful_chars(text: str) -> int:
    collapsed = re.sub(r"\s+", "", text or "")
    return len(collapsed)


def quality_reason(text: str, *, min_meaningful_chars: int) -> str | None:
    if text is None or text.strip() == "":
        return "blank"
    if _blocked_content(text):
        return "blocked"
    if meaningful_chars(text) < min_meaningful_chars:
        return "too_short"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python -m pytest tests/test_public_url_quality.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_public_url_quality.py src/lmit/fetchers/public_url_quality.py
git commit -m "feat: add public url quality checks"
```

### Task 3: Add Scrapling Adapter and Pipeline Orchestration

**Files:**
- Create: `tests/test_public_url_pipeline.py`
- Create: `src/lmit/fetchers/public_url_scrapling.py`
- Modify: `src/lmit/fetchers/public_url.py`

- [ ] **Step 1: Write the failing pipeline tests**

```python
from pathlib import Path

from lmit.config import PublicFetchConfig
from lmit.fetchers.public_url import PublicUrlFetcher
from lmit.reports import ConversionReport


class DummyAdapter:
    def convert_url(self, url: str) -> str:
        return "legacy-url"

    def convert_path(self, path: Path) -> str:
        return "legacy-html"


class FakeScraplingFetcher:
    def __init__(self, static_result=None, dynamic_result=None, static_error=None, dynamic_error=None):
        self.static_result = static_result
        self.dynamic_result = dynamic_result
        self.static_error = static_error
        self.dynamic_error = dynamic_error

    def fetch_static(self, url: str) -> str:
        if self.static_error:
            raise self.static_error
        return self.static_result

    def fetch_dynamic(self, url: str) -> str:
        if self.dynamic_error:
            raise self.dynamic_error
        return self.dynamic_result


def _public_fetch(**overrides):
    base = PublicFetchConfig()
    data = base.__dict__ | overrides
    return PublicFetchConfig(**data)


def test_public_url_uses_scrapling_static_when_quality_is_good(tmp_path: Path):
    report = ConversionReport()
    fetcher = PublicUrlFetcher(
        DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        public_fetch=_public_fetch(min_meaningful_chars=5),
        scrapling_fetcher=FakeScraplingFetcher(static_result="A" * 40),
    )

    assert fetcher.fetch("https://example.com") == "A" * 40
    assert any("provider=scrapling_static" in line for line in report.lines)


def test_public_url_escalates_static_blank_to_dynamic(tmp_path: Path):
    report = ConversionReport()
    fetcher = PublicUrlFetcher(
        DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        public_fetch=_public_fetch(min_meaningful_chars=5),
        scrapling_fetcher=FakeScraplingFetcher(static_result=" ", dynamic_result="A" * 40),
    )

    assert fetcher.fetch("https://example.com") == "A" * 40
    assert any("from=scrapling_static to=scrapling_dynamic reason=blank" in line for line in report.lines)


def test_public_url_falls_back_to_legacy_when_scrapling_fails(tmp_path: Path):
    report = ConversionReport()
    fetcher = PublicUrlFetcher(
        DummyAdapter(),
        work_dir=tmp_path,
        report=report,
        public_fetch=_public_fetch(min_meaningful_chars=5),
        scrapling_fetcher=FakeScraplingFetcher(
            static_error=RuntimeError("static boom"),
            dynamic_error=RuntimeError("dynamic boom"),
        ),
    )

    assert fetcher.fetch("https://example.com") == "legacy-url"
    assert any("to=legacy_markitdown_url" in line for line in report.lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_public_url_pipeline.py -v`  
Expected: FAIL because `PublicUrlFetcher` does not accept `public_fetch` or `scrapling_fetcher`.

- [ ] **Step 3: Write minimal Scrapling adapter**

Create `src/lmit/fetchers/public_url_scrapling.py` with a focused wrapper:

```python
from __future__ import annotations

from dataclasses import dataclass

from lmit.config import PublicFetchConfig


@dataclass(frozen=True)
class ScraplingPublicFetcher:
    config: PublicFetchConfig

    def fetch_static(self, url: str) -> str:
        from scrapling.fetchers import Fetcher

        page = Fetcher.fetch(
            url,
            timeout=self.config.request_timeout_seconds,
            stealthy_headers=True,
        )
        return page.markdown if self.config.scrapling_cleanup == "ai_targeted" else page.text

    def fetch_dynamic(self, url: str) -> str:
        from scrapling.fetchers import DynamicFetcher

        page = DynamicFetcher.fetch(
            url,
            timeout=self.config.navigation_timeout_ms / 1000,
            disable_ads=self.config.scrapling_block_ads,
        )
        return page.markdown if self.config.scrapling_cleanup == "ai_targeted" else page.text
```

Then extend `src/lmit/fetchers/public_url.py` to:

- accept `public_fetch`
- accept `scrapling_fetcher`
- route `provider == "legacy"` to the old logic
- otherwise run the four-stage provider chain

Core orchestration shape:

```python
reason = quality_reason(text, min_meaningful_chars=self.public_fetch.min_meaningful_chars)
if reason is None:
    self.report.log(f"[URL-FETCH-DONE] provider=scrapling_static url={url}")
    return text
self.report.log(
    f"[URL-FETCH-UPGRADE] from=scrapling_static to=scrapling_dynamic reason={reason}"
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python -m pytest tests/test_public_url_pipeline.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_public_url_pipeline.py src/lmit/fetchers/public_url_scrapling.py src/lmit/fetchers/public_url.py
git commit -m "feat: add scrapling public url pipeline"
```

### Task 4: Add Report Counters and Running-Report Visibility

**Files:**
- Modify: `src/lmit/reports.py`
- Modify: `tests/test_reports.py`

- [ ] **Step 1: Write the failing report test**

Add this test to `tests/test_reports.py`:

```python
def test_render_report_includes_public_fetch_stats(tmp_path: Path):
    path = tmp_path / "conversion_report_20260425_020000.json"
    _write_report(
        path,
        stats={
            "public_url_scrapling_static_success": 3,
            "public_url_scrapling_dynamic_success": 2,
            "public_url_markitdown_success": 1,
            "public_url_playwright_success": 1,
            "public_url_quality_retry": 4,
            "public_url_blocked": 2,
            "public_url_blank": 1,
        },
        log=[
            "[URL-FETCH-PROVIDER] provider=scrapling_static url=https://example.com",
            "[URL-FETCH-UPGRADE] from=scrapling_static to=scrapling_dynamic reason=too_short",
        ],
    )

    summary = render_report(load_report(path), summary_only=True)

    assert "- public_url_scrapling_static_success: 3" in summary
    assert "- public_url_quality_retry: 4" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_reports.py::test_render_report_includes_public_fetch_stats -v`  
Expected: FAIL because the stat keys are not in `SUMMARY_STATS`.

- [ ] **Step 3: Write minimal reporting implementation**

In `src/lmit/reports.py`, extend `ConversionStats` and `SUMMARY_STATS`:

```python
public_url_scrapling_static_success: int = 0
public_url_scrapling_dynamic_success: int = 0
public_url_markitdown_success: int = 0
public_url_playwright_success: int = 0
public_url_quality_retry: int = 0
public_url_blocked: int = 0
public_url_blank: int = 0
```

Make `PublicUrlFetcher` increment them at the point each provider succeeds or each quality escalation happens.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python -m pytest tests/test_reports.py::test_render_report_includes_public_fetch_stats -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/lmit/reports.py tests/test_reports.py src/lmit/fetchers/public_url.py
git commit -m "feat: expose public fetch stats in reports"
```

### Task 5: Add Dependency, Example Config, and Docs

**Files:**
- Modify: `pyproject.toml`
- Modify: `config/config.example.toml`
- Modify: `README.md`

- [ ] **Step 1: Write the failing dependency/doc expectations as a checklist**

Add these expected install/documentation snippets:

```toml
[project.optional-dependencies]
scrapling = [
  "scrapling[fetchers]>=0.4,<0.5",
]
```

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

README should add:

```powershell
.\.venv\Scripts\python -m pip install -e ".[scrapling,dev]"
.\.venv\Scripts\python -m scrapling install
```

- [ ] **Step 2: Run focused regression suite before docs change**

Run: `.\.venv\Scripts\python -m pytest tests/test_public_fetch_config.py tests/test_public_url_quality.py tests/test_public_url_pipeline.py tests/test_reports.py -v`  
Expected: PASS before editing docs so the implementation baseline is stable.

- [ ] **Step 3: Write the dependency and docs changes**

Update `pyproject.toml`, `config/config.example.toml`, and `README.md` with:

- the new `scrapling` extra
- install/setup instructions
- an explanation that public URLs use the new pipeline and session sites do not
- the `provider = "legacy"` rollback option

- [ ] **Step 4: Run full test suite**

Run: `.\.venv\Scripts\python -m pytest -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml config/config.example.toml README.md
git commit -m "docs: document scrapling public fetch pipeline"
```

### Task 6: Manual Smoke Verification

**Files:**
- No code changes required

- [ ] **Step 1: Install the new extra**

Run:

```powershell
.\.venv\Scripts\python -m pip install -e ".[scrapling,dev]"
.\.venv\Scripts\python -m scrapling install
```

Expected: installation completes without import errors.

- [ ] **Step 2: Run a legacy baseline batch**

Set:

```toml
[public_fetch]
provider = "legacy"
```

Run:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml --only "public-sample.txt" --overwrite
```

Expected: baseline report is generated using the old public fetch path.

- [ ] **Step 3: Run an auto-provider comparison batch**

Set:

```toml
[public_fetch]
provider = "auto"
```

Run:

```powershell
.\.venv\Scripts\python -m lmit.cli convert --config config/config.example.toml --only "public-sample.txt" --overwrite
```

Expected:

- report contains `[URL-FETCH-PROVIDER]` lines
- report contains upgrade lines when low-quality pages escalate
- output markdown is at least as complete as legacy for the same URLs

- [ ] **Step 4: Compare results**

Check:

- successful URL count
- number of blank outputs
- number of blocked outputs
- amount of obvious ad/footer/nav noise in output markdown

Expected: `auto` is equal or better on success rate and visibly cleaner on noisy public pages.

- [ ] **Step 5: Commit final integration**

```bash
git add pyproject.toml config/config.example.toml README.md src/lmit/config.py src/lmit/fetchers/public_url.py src/lmit/fetchers/public_url_scrapling.py src/lmit/fetchers/public_url_quality.py src/lmit/reports.py tests/test_public_fetch_config.py tests/test_public_url_quality.py tests/test_public_url_pipeline.py tests/test_reports.py
git commit -m "feat: verify scrapling public fetch pipeline"
```

## Self-Review

- Spec coverage:
  - public-only scope: covered in Tasks 1, 3, and 5
  - fallback order: covered in Task 3
  - config: covered in Task 1
  - reporting: covered in Task 4
  - docs and rollout: covered in Tasks 5 and 6
- Placeholder scan:
  - no placeholder markers
  - each task contains exact file paths, commands, and expected outcomes
- Type consistency:
  - `PublicFetchConfig`, `quality_reason`, and `ScraplingPublicFetcher` are used consistently across tasks
