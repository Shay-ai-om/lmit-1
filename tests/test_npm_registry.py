from lmit.fetchers.npm_registry import parse_npm_package_url


def test_parse_npm_package_url_unscoped():
    parsed = parse_npm_package_url("https://www.npmjs.com/package/brainplex")

    assert parsed is not None
    assert parsed.package_name == "brainplex"


def test_parse_npm_package_url_scoped():
    parsed = parse_npm_package_url("https://www.npmjs.com/package/@scope/pkg")

    assert parsed is not None
    assert parsed.package_name == "@scope/pkg"


def test_parse_npm_package_url_ignores_other_hosts():
    assert parse_npm_package_url("https://example.com/package/brainplex") is None
