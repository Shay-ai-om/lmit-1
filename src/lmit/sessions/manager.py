from __future__ import annotations

from urllib.parse import urlparse

from lmit.config import AppConfig, SessionSiteConfig


class SessionManager:
    def __init__(self, cfg: AppConfig):
        self.sites = cfg.sessions

    def site_for_url(self, url: str) -> SessionSiteConfig | None:
        host = (urlparse(url).netloc or "").split("@")[-1].split(":")[0].lower()
        if not host:
            return None
        for site in self.sites:
            if any(_domain_matches(host, domain) for domain in site.domains):
                return site
        return None


def _domain_matches(host: str, domain: str) -> bool:
    normalized = domain.lower().lstrip(".")
    return host == normalized or host.endswith(f".{normalized}")
