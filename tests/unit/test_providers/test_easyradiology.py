import pytest

from medcheck.providers.easyradiology import (
    EasyRadiologyProvider,
    _scrypt_derive,
    _validate_download_url,
    parse_access_code,
)


def test_parse_access_code_four_segments():
    view_code, password = parse_access_code("N6D-8KT-M9F-9JX")
    assert view_code == "N6D-8KT"
    assert password == "M9F-9JX"


def test_parse_access_code_three_segments():
    view_code, password = parse_access_code("A2C-AB3-4BC")
    assert view_code == "A2C-AB3"
    assert password == "4BC"


def test_parse_access_code_too_few_segments():
    with pytest.raises(ValueError, match="Invalid access code"):
        parse_access_code("AB")


def test_provider_url_patterns():
    p = EasyRadiologyProvider()
    assert any("easyradiology" in pat for pat in p.url_patterns)


def test_extract_exam_hash():
    p = EasyRadiologyProvider()
    url = "https://portal.easyradiology.net/View/dz8dzkg9-4hzcaosn-z5uq61yo-ubnsdthy"
    assert p._extract_exam_hash(url) == "dz8dzkg9-4hzcaosn-z5uq61yo-ubnsdthy"


def test_extract_exam_hash_trailing_slash():
    p = EasyRadiologyProvider()
    url = "https://portal.easyradiology.net/View/abc123/"
    assert p._extract_exam_hash(url) == "abc123"


def test_scrypt_derive_deterministic():
    key1 = _scrypt_derive("test", b"salt1234")
    key2 = _scrypt_derive("test", b"salt1234")
    assert key1 == key2
    assert len(key1) == 32


def test_scrypt_derive_different_passwords():
    key1 = _scrypt_derive("pass1", b"salt1234")
    key2 = _scrypt_derive("pass2", b"salt1234")
    assert key1 != key2


def test_authenticate_requires_code_and_dob():
    p = EasyRadiologyProvider()
    assert p.authenticate({"code": "ABC", "dob": "01.01.2000"}) is True
    assert p.authenticate({"code": "ABC"}) is False
    assert p.authenticate({}) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://portal.easyradiology.net/download/exam.zip",
        "https://cdn.easyradiology.de/files/exam.zip",
        "https://easyradiology.net/exam.zip",
    ],
)
def test_validate_download_url_accepts_trusted_https(url):
    # Should not raise.
    _validate_download_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://portal.easyradiology.net/exam.zip",  # not https
        "https://evil.example.com/exam.zip",  # untrusted host
        "https://127.0.0.1/exam.zip",  # loopback (SSRF)
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata (SSRF)
        "https://easyradiology.net.evil.com/exam.zip",  # suffix-spoof attempt
        "file:///etc/passwd",  # non-http scheme
    ],
)
def test_validate_download_url_rejects_untrusted(url):
    with pytest.raises(ValueError):
        _validate_download_url(url)
