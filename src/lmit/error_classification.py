from __future__ import annotations

from dataclasses import dataclass

from lmit.path_safety import PathSafetyError


@dataclass(frozen=True)
class ErrorClassification:
    error_type: str
    retryable: bool


def classify_error(exc: Exception) -> ErrorClassification:
    name = exc.__class__.__name__.lower()
    module = exc.__class__.__module__.lower()
    message = str(exc).lower()
    haystack = f"{module} {name} {message}"

    if isinstance(exc, PathSafetyError):
        return ErrorClassification("path_safety_error", False)
    if isinstance(exc, (FileNotFoundError, PermissionError)):
        return ErrorClassification("filesystem_error", True)
    if "sessionloginrequired" in haystack or "session expired" in haystack:
        return ErrorClassification("session_expired", True)
    if "timeout" in haystack or "connection" in haystack or "network" in haystack:
        return ErrorClassification("network", True)
    if "unsupported" in haystack or "no converter" in haystack or "format" in haystack:
        return ErrorClassification("unsupported_format", False)
    return ErrorClassification("conversion_error", True)
