from lmit.converters.txt_urls import _blocked_content, extract_urls


def test_extract_urls_dedupes_and_trims_punctuation():
    text = "See https://example.com/a), and https://example.com/a plus https://x.test?q=1."

    assert extract_urls(text) == ["https://example.com/a", "https://x.test?q=1"]


def test_blocked_content_detects_cloudflare_challenge():
    text = "Performing security verification. Enable JavaScript and cookies to continue."

    assert _blocked_content(text)


def test_blocked_content_detects_facebook_unavailable_message():
    text = "目前無法查看此內容，通常是因為擁有者僅與一小群用戶分享內容。"

    assert _blocked_content(text)
