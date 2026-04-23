from __future__ import annotations

from lmit.config import SessionSiteConfig
from lmit.sessions.strategies.base import DefaultSessionStrategy
from lmit.sessions.strategies.facebook import FacebookSessionStrategy, is_facebook_site


def strategy_for_site(site: SessionSiteConfig):
    if is_facebook_site(site):
        return FacebookSessionStrategy(site)
    return DefaultSessionStrategy(site)


__all__ = [
    "DefaultSessionStrategy",
    "FacebookSessionStrategy",
    "is_facebook_site",
    "strategy_for_site",
]
