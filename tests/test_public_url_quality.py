from lmit.fetchers.public_url_quality import (
    count_meaningful_visible_chars,
    is_blank_public_url_text,
    is_blocked_public_url_text,
    is_too_short_public_url_text,
)


def test_blank_public_url_text_detects_none_and_whitespace():
    assert is_blank_public_url_text(None)
    assert is_blank_public_url_text("")
    assert is_blank_public_url_text("   \n\t  ")
    assert count_meaningful_visible_chars("   \n\t  ") == 0
    assert not is_too_short_public_url_text("   \n\t  ", min_meaningful_chars=200)


def test_blocked_public_url_text_reuses_repo_markers():
    assert is_blocked_public_url_text("Just a moment... checking your browser")
    assert is_blocked_public_url_text("百度安全验证\n请完成下方验证后继续操作")


def test_too_short_public_url_text_uses_meaningful_visible_chars():
    text = "a" * 199

    assert count_meaningful_visible_chars(text) == 199
    assert is_too_short_public_url_text(text, min_meaningful_chars=200)


def test_acceptable_public_url_text_is_not_flagged():
    text = "a" * 200

    assert count_meaningful_visible_chars(text) == 200
    assert not is_blank_public_url_text(text)
    assert not is_blocked_public_url_text(text)
    assert not is_too_short_public_url_text(text, min_meaningful_chars=200)
