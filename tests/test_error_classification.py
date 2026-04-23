from __future__ import annotations

from lmit.error_classification import classify_error
from lmit.path_safety import PathSafetyError


def test_classify_path_safety_error_is_not_retryable():
    result = classify_error(PathSafetyError("escape"))

    assert result.error_type == "path_safety_error"
    assert result.retryable is False


def test_classify_timeout_as_retryable_network_error():
    result = classify_error(TimeoutError("network timeout"))

    assert result.error_type == "network"
    assert result.retryable is True


def test_classify_unsupported_as_non_retryable():
    result = classify_error(RuntimeError("unsupported file format"))

    assert result.error_type == "unsupported_format"
    assert result.retryable is False
