from __future__ import annotations

from collections.abc import Callable


class ConversionCancelled(RuntimeError):
    """Raised when a conversion run is cancelled by the caller."""


CancelCheck = Callable[[], None]


def noop_cancel_check() -> None:
    return None

