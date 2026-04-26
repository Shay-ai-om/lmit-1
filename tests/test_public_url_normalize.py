from lmit.fetchers.public_url_normalize import normalize_public_url


def test_normalize_public_url_strips_tracking_mobile_params_for_tieba():
    normalized = normalize_public_url(
        "https://tieba.baidu.com/p/9152102978?lp=5027&mo_device=1&is_jingpost=0"
        "&fbclid=abc123#/detail"
    )

    assert normalized.url == "https://tieba.baidu.com/p/9152102978?lp=5027"
    assert normalized.reasons == (
        "drop_query:mo_device",
        "drop_query:is_jingpost",
        "drop_query:fbclid",
        "drop_fragment",
    )


def test_normalize_public_url_keeps_unrelated_query_params():
    normalized = normalize_public_url("https://example.com/article?id=123&page=2")

    assert normalized.url == "https://example.com/article?id=123&page=2"
    assert normalized.reasons == ()
