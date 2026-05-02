from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
import tomllib


DEFAULT_SUPPORTED_EXTS = {
    ".md",
    ".markdown",
    ".txt",
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".jpg",
    ".jpeg",
    ".png",
}

DEFAULT_EXCLUDE_GLOBS = [
    ".git/**",
    ".venv/**",
    "output/**",
    ".lmit_work/**",
    "sessions/**",
    "__pycache__/**",
    "*.zip",
    "*.7z",
    "*.rar",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*key*.json",
    "*credential*.json",
    "*secret*",
    "*token*",
    ".env",
]


@dataclass(frozen=True)
class PathsConfig:
    input_dirs: tuple[Path, ...]
    output_dir: Path
    work_dir: Path
    report_dir: Path
    session_dir: Path

    @property
    def input_dir(self) -> Path:
        return self.input_dirs[0]


@dataclass(frozen=True)
class ScanConfig:
    recursive: bool
    supported_exts: set[str]
    exclude_globs: list[str]


@dataclass(frozen=True)
class ConversionConfig:
    enable_markitdown_plugins: bool
    fetch_urls: bool
    overwrite: bool
    skip_unchanged: bool
    blank_note_for_images: bool
    only_patterns: tuple[str, ...] = ()
    retry_failed: bool = False


@dataclass(frozen=True)
class PublicFetchConfig:
    provider: str = "auto"
    enable_scrapling: bool = True
    enable_scrapling_dynamic: bool = True
    enable_scrapling_stealthy: bool = False
    enable_scrapling_stealthy_on_cloudflare: bool = True
    scrapling_stealthy_solve_cloudflare: bool = True
    scrapling_cleanup: str = "ai_targeted"
    scrapling_block_ads: bool = True
    request_timeout_seconds: int = 30
    navigation_timeout_ms: int = 45000
    min_meaningful_chars: int = 200
    browser_channel: str | None = None
    browser_executable_path: Path | None = None
    browser_connect_over_cdp: bool = False
    browser_cdp_port: int | None = None
    public_browser_auto_launch: bool = True
    public_browser_profile_dir: Path | None = None
    cdp_first_domains: tuple[str, ...] = ("baidu.com",)


@dataclass(frozen=True)
class MarkItDownConfig:
    llm_enabled: bool = False
    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_model: str | None = None
    llm_api_key_env: str = "OPENAI_API_KEY"
    llm_prompt: str | None = None


@dataclass(frozen=True)
class PollingConfig:
    enabled: bool
    interval_seconds: int
    stable_seconds: int


@dataclass(frozen=True)
class OutputNamingConfig:
    enrich_filenames: bool
    prefix_source: str
    max_prefix_chars: int
    separator: str


@dataclass(frozen=True)
class WikiConfig:
    root_dir: Path
    raw_dir: Path
    sources_dir: Path
    topics_dir: Path
    entities_dir: Path
    queries_dir: Path
    schema_dir: Path
    log_path: Path
    index_path: Path


@dataclass(frozen=True)
class WikiIngestConfig:
    source_dirs: tuple[Path, ...]


@dataclass(frozen=True)
class WikiRuntimeConfig:
    settings_path: Path
    state_path: Path
    auto_sync_on_ingest: bool
    search_limit: int
    serve_host: str
    serve_port: int


@dataclass(frozen=True)
class SessionSiteConfig:
    name: str
    domains: list[str]
    login_url: str
    state_file: Path
    headless: bool
    wait_ms: int
    render_mode: str = "desktop"
    navigation_timeout_ms: int = 90000
    retry_count: int = 2
    retry_backoff_ms: int = 1500
    browser_channel: str | None = None
    browser_executable_path: Path | None = None
    login_use_persistent_context: bool = False
    login_persistent_profile_dir: Path | None = None
    login_connect_over_cdp: bool = False
    login_cdp_port: int | None = None


@dataclass(frozen=True)
class AppConfig:
    paths: PathsConfig
    scan: ScanConfig
    conversion: ConversionConfig
    public_fetch: PublicFetchConfig
    markitdown: MarkItDownConfig
    polling: PollingConfig
    output_naming: OutputNamingConfig
    wiki: WikiConfig
    wiki_ingest: WikiIngestConfig
    wiki_runtime: WikiRuntimeConfig
    sessions: list[SessionSiteConfig]


def default_config(cwd: Path | None = None) -> AppConfig:
    base = (cwd or Path.cwd()).resolve()
    wiki_root = base / "knowledge_base"
    return AppConfig(
        paths=PathsConfig(
            input_dirs=(base / "input",),
            output_dir=base / "output" / "raw",
            work_dir=base / ".lmit_work",
            report_dir=base / "output" / "reports",
            session_dir=base / "sessions",
        ),
        scan=ScanConfig(
            recursive=True,
            supported_exts=set(DEFAULT_SUPPORTED_EXTS),
            exclude_globs=list(DEFAULT_EXCLUDE_GLOBS),
        ),
        conversion=ConversionConfig(
            enable_markitdown_plugins=True,
            fetch_urls=True,
            overwrite=False,
            skip_unchanged=True,
            blank_note_for_images=True,
            only_patterns=(),
            retry_failed=False,
        ),
        public_fetch=PublicFetchConfig(),
        markitdown=MarkItDownConfig(),
        polling=PollingConfig(enabled=False, interval_seconds=300, stable_seconds=10),
        output_naming=OutputNamingConfig(
            enrich_filenames=False,
            prefix_source="auto",
            max_prefix_chars=64,
            separator="__",
        ),
        wiki=WikiConfig(
            root_dir=wiki_root,
            raw_dir=wiki_root / "raw",
            sources_dir=wiki_root / "wiki" / "sources",
            topics_dir=wiki_root / "wiki" / "topics",
            entities_dir=wiki_root / "wiki" / "entities",
            queries_dir=wiki_root / "wiki" / "queries",
            schema_dir=wiki_root / "schema",
            log_path=wiki_root / "wiki" / "log.md",
            index_path=wiki_root / "wiki" / "index.md",
        ),
        wiki_ingest=WikiIngestConfig(
            source_dirs=(base / "output" / "raw",),
        ),
        wiki_runtime=WikiRuntimeConfig(
            settings_path=wiki_root / ".wiki_runtime.json",
            state_path=wiki_root / ".wiki_state.json",
            auto_sync_on_ingest=False,
            search_limit=8,
            serve_host="127.0.0.1",
            serve_port=8765,
        ),
        sessions=[
            SessionSiteConfig(
                name="facebook",
                domains=[
                    "facebook.com",
                    "www.facebook.com",
                    "m.facebook.com",
                    "mbasic.facebook.com",
                ],
                login_url="https://www.facebook.com/login",
                state_file=base / "sessions" / "facebook_state.json",
                headless=True,
                wait_ms=8000,
                render_mode="desktop",
                navigation_timeout_ms=90000,
                retry_count=2,
                retry_backoff_ms=1500,
                browser_channel=None,
                browser_executable_path=None,
                login_use_persistent_context=False,
                login_persistent_profile_dir=None,
                login_connect_over_cdp=False,
                login_cdp_port=None,
            )
        ],
    )


def load_config(path: Path | None = None, cwd: Path | None = None) -> AppConfig:
    cfg = default_config(cwd=cwd)
    if path is None:
        return cfg

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    base = (cwd or Path.cwd()).resolve()

    paths_data = data.get("paths", {})
    input_dirs_value = paths_data.get("input_dirs")
    if input_dirs_value is None:
        input_dirs_value = paths_data.get("input_dir")
    paths = PathsConfig(
        input_dirs=_resolve_paths(input_dirs_value, cfg.paths.input_dirs, base),
        output_dir=_resolve_path(paths_data.get("output_dir"), cfg.paths.output_dir, base),
        work_dir=_resolve_path(paths_data.get("work_dir"), cfg.paths.work_dir, base),
        report_dir=_resolve_path(paths_data.get("report_dir"), cfg.paths.report_dir, base),
        session_dir=_resolve_path(paths_data.get("session_dir"), cfg.paths.session_dir, base),
    )

    scan_data = data.get("scan", {})
    scan = ScanConfig(
        recursive=bool(scan_data.get("recursive", cfg.scan.recursive)),
        supported_exts=_normalize_exts(scan_data.get("supported_exts", cfg.scan.supported_exts)),
        exclude_globs=list(scan_data.get("exclude_globs", cfg.scan.exclude_globs)),
    )

    conversion_data = data.get("conversion", {})
    conversion = ConversionConfig(
        enable_markitdown_plugins=bool(
            conversion_data.get(
                "enable_markitdown_plugins", cfg.conversion.enable_markitdown_plugins
            )
        ),
        fetch_urls=bool(conversion_data.get("fetch_urls", cfg.conversion.fetch_urls)),
        overwrite=bool(conversion_data.get("overwrite", cfg.conversion.overwrite)),
        skip_unchanged=bool(
            conversion_data.get("skip_unchanged", cfg.conversion.skip_unchanged)
        ),
        blank_note_for_images=bool(
            conversion_data.get(
                "blank_note_for_images", cfg.conversion.blank_note_for_images
            )
        ),
        only_patterns=tuple(
            str(item) for item in conversion_data.get("only_patterns", cfg.conversion.only_patterns)
        ),
        retry_failed=bool(conversion_data.get("retry_failed", cfg.conversion.retry_failed)),
    )

    public_fetch_data = data.get("public_fetch", {})
    public_fetch = PublicFetchConfig(
        provider=str(public_fetch_data.get("provider", cfg.public_fetch.provider)),
        enable_scrapling=bool(
            public_fetch_data.get("enable_scrapling", cfg.public_fetch.enable_scrapling)
        ),
        enable_scrapling_dynamic=bool(
            public_fetch_data.get(
                "enable_scrapling_dynamic",
                cfg.public_fetch.enable_scrapling_dynamic,
            )
        ),
        enable_scrapling_stealthy=bool(
            public_fetch_data.get(
                "enable_scrapling_stealthy",
                cfg.public_fetch.enable_scrapling_stealthy,
            )
        ),
        enable_scrapling_stealthy_on_cloudflare=bool(
            public_fetch_data.get(
                "enable_scrapling_stealthy_on_cloudflare",
                cfg.public_fetch.enable_scrapling_stealthy_on_cloudflare,
            )
        ),
        scrapling_stealthy_solve_cloudflare=bool(
            public_fetch_data.get(
                "scrapling_stealthy_solve_cloudflare",
                cfg.public_fetch.scrapling_stealthy_solve_cloudflare,
            )
        ),
        scrapling_cleanup=str(
            public_fetch_data.get("scrapling_cleanup", cfg.public_fetch.scrapling_cleanup)
        ),
        scrapling_block_ads=bool(
            public_fetch_data.get(
                "scrapling_block_ads",
                cfg.public_fetch.scrapling_block_ads,
            )
        ),
        request_timeout_seconds=int(
            public_fetch_data.get(
                "request_timeout_seconds",
                cfg.public_fetch.request_timeout_seconds,
            )
        ),
        navigation_timeout_ms=int(
            public_fetch_data.get(
                "navigation_timeout_ms",
                cfg.public_fetch.navigation_timeout_ms,
            )
        ),
        min_meaningful_chars=int(
            public_fetch_data.get(
                "min_meaningful_chars",
                cfg.public_fetch.min_meaningful_chars,
            )
        ),
        browser_channel=_optional_string(
            public_fetch_data.get("browser_channel", cfg.public_fetch.browser_channel)
        ),
        browser_executable_path=_resolve_optional_path(
            public_fetch_data.get("browser_executable_path"),
            default=base / "public-browser.exe",
            base=base,
        ),
        browser_connect_over_cdp=bool(
            public_fetch_data.get(
                "browser_connect_over_cdp",
                cfg.public_fetch.browser_connect_over_cdp,
            )
        ),
        browser_cdp_port=_optional_int(
            public_fetch_data.get("browser_cdp_port", cfg.public_fetch.browser_cdp_port)
        ),
        public_browser_auto_launch=bool(
            public_fetch_data.get(
                "public_browser_auto_launch",
                cfg.public_fetch.public_browser_auto_launch,
            )
        ),
        public_browser_profile_dir=_resolve_optional_path(
            public_fetch_data.get("public_browser_profile_dir"),
            default=paths.work_dir / "browser_profiles" / "public",
            base=base,
        ),
        cdp_first_domains=tuple(
            _normalize_domain(item)
            for item in public_fetch_data.get(
                "cdp_first_domains",
                cfg.public_fetch.cdp_first_domains,
            )
            if _normalize_domain(item)
        ),
    )

    markitdown_data = data.get("markitdown", {})
    markitdown = MarkItDownConfig(
        llm_enabled=bool(markitdown_data.get("llm_enabled", cfg.markitdown.llm_enabled)),
        llm_provider=str(markitdown_data.get("llm_provider", cfg.markitdown.llm_provider)),
        llm_base_url=str(markitdown_data.get("llm_base_url", cfg.markitdown.llm_base_url)),
        llm_model=_optional_string(markitdown_data.get("llm_model", cfg.markitdown.llm_model)),
        llm_api_key_env=str(
            markitdown_data.get("llm_api_key_env", cfg.markitdown.llm_api_key_env)
        ),
        llm_prompt=_optional_string(markitdown_data.get("llm_prompt", cfg.markitdown.llm_prompt)),
    )

    polling_data = data.get("polling", {})
    polling = PollingConfig(
        enabled=bool(polling_data.get("enabled", cfg.polling.enabled)),
        interval_seconds=int(
            polling_data.get("interval_seconds", cfg.polling.interval_seconds)
        ),
        stable_seconds=int(polling_data.get("stable_seconds", cfg.polling.stable_seconds)),
    )

    output_naming_data = data.get("output_naming", {})
    output_naming = OutputNamingConfig(
        enrich_filenames=bool(
            output_naming_data.get(
                "enrich_filenames",
                cfg.output_naming.enrich_filenames,
            )
        ),
        prefix_source=str(
            output_naming_data.get("prefix_source", cfg.output_naming.prefix_source)
        ),
        max_prefix_chars=int(
            output_naming_data.get(
                "max_prefix_chars",
                cfg.output_naming.max_prefix_chars,
            )
        ),
        separator=str(output_naming_data.get("separator", cfg.output_naming.separator)),
    )

    wiki_data = data.get("wiki", {})
    wiki_root = _resolve_path(wiki_data.get("root_dir"), cfg.wiki.root_dir, base)
    wiki = WikiConfig(
        root_dir=wiki_root,
        raw_dir=_resolve_path(wiki_data.get("raw_dir"), wiki_root / "raw", base),
        sources_dir=_resolve_path(
            wiki_data.get("sources_dir"), wiki_root / "wiki" / "sources", base
        ),
        topics_dir=_resolve_path(
            wiki_data.get("topics_dir"), wiki_root / "wiki" / "topics", base
        ),
        entities_dir=_resolve_path(
            wiki_data.get("entities_dir"), wiki_root / "wiki" / "entities", base
        ),
        queries_dir=_resolve_path(
            wiki_data.get("queries_dir"), wiki_root / "wiki" / "queries", base
        ),
        schema_dir=_resolve_path(wiki_data.get("schema_dir"), wiki_root / "schema", base),
        log_path=_resolve_path(wiki_data.get("log_path"), wiki_root / "wiki" / "log.md", base),
        index_path=_resolve_path(
            wiki_data.get("index_path"), wiki_root / "wiki" / "index.md", base
        ),
    )

    wiki_ingest_data = data.get("wiki_ingest", {})
    wiki_ingest = WikiIngestConfig(
        source_dirs=_resolve_paths(
            wiki_ingest_data.get("source_dirs"),
            cfg.wiki_ingest.source_dirs,
            base,
        ),
    )

    wiki_runtime_data = data.get("wiki_runtime", {})
    wiki_runtime = WikiRuntimeConfig(
        settings_path=_resolve_path(
            wiki_runtime_data.get("settings_path"),
            cfg.wiki_runtime.settings_path,
            base,
        ),
        state_path=_resolve_path(
            wiki_runtime_data.get("state_path"),
            cfg.wiki_runtime.state_path,
            base,
        ),
        auto_sync_on_ingest=bool(
            wiki_runtime_data.get(
                "auto_sync_on_ingest",
                cfg.wiki_runtime.auto_sync_on_ingest,
            )
        ),
        search_limit=int(
            wiki_runtime_data.get("search_limit", cfg.wiki_runtime.search_limit)
        ),
        serve_host=str(
            wiki_runtime_data.get("serve_host", cfg.wiki_runtime.serve_host)
        ),
        serve_port=int(
            wiki_runtime_data.get("serve_port", cfg.wiki_runtime.serve_port)
        ),
    )

    sessions = [
        _load_session_site(item, paths.session_dir, base) for item in data.get("sessions", [])
    ]
    if not sessions:
        sessions = cfg.sessions

    return AppConfig(
        paths=paths,
        scan=scan,
        conversion=conversion,
        public_fetch=public_fetch,
        markitdown=markitdown,
        polling=polling,
        output_naming=output_naming,
        wiki=wiki,
        wiki_ingest=wiki_ingest,
        wiki_runtime=wiki_runtime,
        sessions=sessions,
    )


def with_overrides(
    cfg: AppConfig,
    *,
    input_dir: str | None = None,
    input_dirs: Sequence[str] | None = None,
    output_dir: str | None = None,
    work_dir: str | None = None,
    fetch_urls: bool | None = None,
    overwrite: bool | None = None,
    skip_unchanged: bool | None = None,
    enrich_filenames: bool | None = None,
    only_patterns: Sequence[str] | None = None,
    retry_failed: bool | None = None,
    cwd: Path | None = None,
) -> AppConfig:
    base = (cwd or Path.cwd()).resolve()
    paths = cfg.paths
    if input_dirs is not None:
        paths = replace(paths, input_dirs=_resolve_paths(input_dirs, paths.input_dirs, base))
    elif input_dir is not None:
        paths = replace(paths, input_dirs=_resolve_paths(input_dir, paths.input_dirs, base))
    if output_dir is not None:
        paths = replace(paths, output_dir=_resolve_path(output_dir, paths.output_dir, base))
    if work_dir is not None:
        paths = replace(paths, work_dir=_resolve_path(work_dir, paths.work_dir, base))

    conversion = cfg.conversion
    if fetch_urls is not None:
        conversion = replace(conversion, fetch_urls=fetch_urls)
    if overwrite is not None:
        conversion = replace(conversion, overwrite=overwrite)
    if skip_unchanged is not None:
        conversion = replace(conversion, skip_unchanged=skip_unchanged)
    if only_patterns is not None:
        conversion = replace(conversion, only_patterns=tuple(only_patterns))
    if retry_failed is not None:
        conversion = replace(conversion, retry_failed=retry_failed)

    output_naming = cfg.output_naming
    if enrich_filenames is not None:
        output_naming = replace(output_naming, enrich_filenames=enrich_filenames)

    return replace(cfg, paths=paths, conversion=conversion, output_naming=output_naming)


def _load_session_site(
    data: dict[str, Any], session_dir: Path, base: Path
) -> SessionSiteConfig:
    name = str(data["name"])
    default_state = session_dir / f"{name}_state.json"
    return SessionSiteConfig(
        name=name,
        domains=[str(item).lower() for item in data.get("domains", [])],
        login_url=str(data["login_url"]),
        state_file=_resolve_path(data.get("state_file"), default_state, base),
        headless=bool(data.get("headless", True)),
        wait_ms=int(data.get("wait_ms", 8000)),
        render_mode=str(data.get("render_mode", "desktop")).lower(),
        navigation_timeout_ms=int(data.get("navigation_timeout_ms", 90000)),
        retry_count=int(data.get("retry_count", 2)),
        retry_backoff_ms=int(data.get("retry_backoff_ms", 1500)),
        browser_channel=_optional_string(data.get("browser_channel")),
        browser_executable_path=_resolve_optional_path(
            data.get("browser_executable_path"),
            default=session_dir / f"{name}.exe",
            base=base,
        ),
        login_use_persistent_context=bool(data.get("login_use_persistent_context", False)),
        login_persistent_profile_dir=_resolve_optional_path(
            data.get("login_persistent_profile_dir"),
            default=session_dir / name,
            base=base,
        ),
        login_connect_over_cdp=bool(data.get("login_connect_over_cdp", False)),
        login_cdp_port=_optional_int(data.get("login_cdp_port")),
    )


def _resolve_path(value: str | None, default: Path, base: Path) -> Path:
    if value is None:
        return default.resolve()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _resolve_optional_path(value: Any, *, default: Path, base: Path) -> Path | None:
    text = _optional_string(value)
    if text is None:
        return None
    return _resolve_path(text, default, base)


def _resolve_paths(value: Any, default: tuple[Path, ...], base: Path) -> tuple[Path, ...]:
    if value is None:
        return tuple(path.resolve() for path in default)
    if isinstance(value, (str, Path)):
        raw_items = [value]
    else:
        raw_items = list(value)

    paths: list[Path] = []
    seen: set[Path] = set()
    for item in raw_items:
        resolved = _resolve_path(str(item), base / "input", base)
        if resolved in seen:
            continue
        paths.append(resolved)
        seen.add(resolved)
    if not paths:
        raise ValueError("at least one input directory must be configured")
    return tuple(paths)


def _normalize_exts(items: Any) -> set[str]:
    return {
        str(item).lower() if str(item).startswith(".") else f".{item}".lower()
        for item in items
    }


def _normalize_domain(value: Any) -> str:
    text = str(value).strip().lower().rstrip(".")
    if text.startswith("http://") or text.startswith("https://"):
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0].split(":", 1)[0].lstrip(".")
    return text


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
