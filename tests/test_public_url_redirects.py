from lmit.fetchers.public_url_redirects import resolve_public_url_redirect


def test_resolve_public_url_redirect_follows_search_app(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        url = "https://sspai.com/post/83644"

        def close(self):
            captured["closed"] = True

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("lmit.fetchers.public_url_redirects.requests.get", fake_get)

    result = resolve_public_url_redirect(
        "https://search.app/PsqCukaJyRGoUVKq9",
        timeout_seconds=7,
    )

    assert result == "https://sspai.com/post/83644"
    assert captured["url"] == "https://search.app/PsqCukaJyRGoUVKq9"
    assert captured["kwargs"]["allow_redirects"] is True
    assert captured["kwargs"]["stream"] is True
    assert captured["kwargs"]["timeout"] == 7
    assert captured["closed"] is True


def test_resolve_public_url_redirect_ignores_regular_urls(monkeypatch):
    def fake_get(url, **kwargs):
        raise AssertionError("regular URLs should not trigger redirect probing")

    monkeypatch.setattr("lmit.fetchers.public_url_redirects.requests.get", fake_get)

    assert resolve_public_url_redirect("https://example.com/article", timeout_seconds=7) is None
