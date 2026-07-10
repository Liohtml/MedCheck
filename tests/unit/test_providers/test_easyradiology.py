from base64 import b64encode
from unittest.mock import MagicMock, patch

import pytest

from medcheck.providers.easyradiology import (
    _MAX_DOWNLOAD_BYTES,
    EasyRadiologyProvider,
    _check_content_length,
    _decrypt_aes_cbc,
    _scrypt_derive,
    _validate_download_url,
    _write_capped,
    parse_access_code,
)


class _Sink:
    """Minimal file-like object that records bytes written."""

    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, chunk: bytes) -> None:
        self.data.extend(chunk)


def test_write_capped_allows_within_limit():
    sink = _Sink()
    written = _write_capped([b"aaaa", b"bbbb"], sink, max_bytes=16)
    assert written == 8
    assert bytes(sink.data) == b"aaaabbbb"


def test_write_capped_aborts_when_exceeded():
    sink = _Sink()
    # Streamed body exceeds the cap even though no single chunk does.
    with pytest.raises(ValueError, match="exceeded"):
        _write_capped([b"x" * 6, b"x" * 6], sink, max_bytes=10)


def test_check_content_length_rejects_oversized_header():
    with pytest.raises(ValueError, match="too large"):
        _check_content_length(str(_MAX_DOWNLOAD_BYTES + 1), _MAX_DOWNLOAD_BYTES)


def test_check_content_length_allows_missing_or_small():
    # None (absent header) and a small/garbage value must not raise.
    _check_content_length(None, _MAX_DOWNLOAD_BYTES)
    _check_content_length("123", _MAX_DOWNLOAD_BYTES)
    _check_content_length("not-a-number", _MAX_DOWNLOAD_BYTES)


def _mock_httpx_client_streaming(chunks: list[bytes], headers: dict[str, str]) -> MagicMock:
    """Build a MagicMock standing in for httpx.Client whose stream() yields *chunks*."""
    resp = MagicMock()
    resp.headers = headers
    resp.raise_for_status = MagicMock()
    resp.iter_bytes = MagicMock(return_value=chunks)

    stream_cm = MagicMock()
    stream_cm.__enter__ = MagicMock(return_value=resp)
    stream_cm.__exit__ = MagicMock(return_value=False)

    client = MagicMock()
    client.stream = MagicMock(return_value=stream_cm)
    client_cm = MagicMock()
    client_cm.__enter__ = MagicMock(return_value=client)
    client_cm.__exit__ = MagicMock(return_value=False)
    return client_cm


def test_download_and_decrypt_aborts_on_oversized_stream(monkeypatch):
    # End-to-end through _download_and_decrypt: a body larger than the configured
    # cap must abort with ValueError before the ZIP is handed to LocalProvider.
    monkeypatch.setenv("MEDCHECK_MAX_DOWNLOAD_BYTES", "10")
    provider = EasyRadiologyProvider()
    client_cm = _mock_httpx_client_streaming([b"x" * 6, b"x" * 6], headers={})  # 12 bytes > 10

    with patch("medcheck.providers.easyradiology.httpx.Client", return_value=client_cm):
        with pytest.raises(ValueError, match="exceeded"):
            provider._download_and_decrypt("https://portal.easyradiology.net/exam.zip", "key", "hash")


def test_download_and_decrypt_rejects_oversized_content_length(monkeypatch):
    # The advertised Content-Length alone (before any bytes stream) must abort.
    monkeypatch.setenv("MEDCHECK_MAX_DOWNLOAD_BYTES", "10")
    provider = EasyRadiologyProvider()
    client_cm = _mock_httpx_client_streaming([b"x"], headers={"Content-Length": "999"})

    with patch("medcheck.providers.easyradiology.httpx.Client", return_value=client_cm):
        with pytest.raises(ValueError, match="too large"):
            provider._download_and_decrypt("https://portal.easyradiology.net/exam.zip", "key", "hash")


def test_decrypt_aes_cbc_round_trip():
    """Verify the AES-CBC + PKCS7 decryption path against a known ciphertext."""
    from Crypto.Cipher import AES  # pycryptodome

    password = "N6D-8KT-M9F-9JX"
    salt = b"0123456789abcdef"
    iv = b"sixteen byte iv!"
    plaintext = b"access-key-payload-12345"

    key = _scrypt_derive(password, salt)
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len]) * pad_len
    ciphertext = AES.new(key, AES.MODE_CBC, iv).encrypt(padded)

    recovered = _decrypt_aes_cbc(
        b64encode(ciphertext).decode(),
        password,
        salt.hex(),
        b64encode(iv).decode(),
    )
    assert recovered == plaintext


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


def test_parse_access_code_error_does_not_leak_credential():
    # The raw access code must never appear in the exception message (#30).
    secret = "SUPERSECRETCODE"
    with pytest.raises(ValueError) as exc:
        parse_access_code(secret)
    assert secret not in str(exc.value)


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


def test_authenticate_requires_only_code():
    # #31: the access code authenticates; dob is not used and must not gate access.
    p = EasyRadiologyProvider()
    assert p.authenticate({"code": "ABC", "dob": "01.01.2000"}) is True
    assert p.authenticate({"code": "ABC"}) is True
    assert p.authenticate({"code": ""}) is False
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


# ---------------------------------------------------------------------------
# Portal orchestration (mocked httpx) — #139
# ---------------------------------------------------------------------------

VALID_CODE = "dz8d-zkg9-4hzc-aosn"


def _mock_httpx_client_post(json_data=None, json_exc=None) -> MagicMock:
    """Build a MagicMock standing in for httpx.Client whose post() returns *json_data*."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    if json_exc is not None:
        resp.json.side_effect = json_exc
    else:
        resp.json.return_value = json_data
    client = MagicMock()
    client.post.return_value = resp
    client_cm = MagicMock()
    client_cm.__enter__ = MagicMock(return_value=client)
    client_cm.__exit__ = MagicMock(return_value=False)
    return client_cm


def _check_view_code_with(json_data=None, json_exc=None) -> str:
    provider = EasyRadiologyProvider()
    client_cm = _mock_httpx_client_post(json_data=json_data, json_exc=json_exc)
    with patch("medcheck.providers.easyradiology.httpx.Client", return_value=client_cm):
        return provider._check_view_code(VALID_CODE, "examhash")


def test_check_view_code_non_json_body():
    with pytest.raises(RuntimeError, match="not JSON"):
        _check_view_code_with(json_exc=ValueError("Expecting value"))


def test_check_view_code_empty_exams():
    with pytest.raises(ValueError, match="No exams found"):
        _check_view_code_with(json_data={"exams": []})


def test_check_view_code_non_dict_payload():
    with pytest.raises(ValueError, match="No exams found"):
        _check_view_code_with(json_data=[1, 2, 3])


def test_check_view_code_missing_encrypted_key():
    with pytest.raises(RuntimeError, match="portal API may have changed"):
        _check_view_code_with(json_data={"exams": [{"somethingElse": True}]})


def test_check_view_code_undecryptable_key_hints_wrong_code():
    import json as jsonlib

    enc = jsonlib.dumps(
        {
            "CipherOutputText": b64encode(b"x" * 16).decode(),  # garbage ciphertext
            "Salt": "00" * 16,
            "AesRijndaelIv": b64encode(b"\x00" * 16).decode(),
        }
    )
    with pytest.raises(ValueError, match="access code may be wrong"):
        _check_view_code_with(json_data={"exams": [{"encryptedAccessKey": enc}]})


def _get_viewer_model_with(json_data=None, json_exc=None):
    provider = EasyRadiologyProvider()
    client_cm = _mock_httpx_client_post(json_data=json_data, json_exc=json_exc)
    with patch("medcheck.providers.easyradiology.httpx.Client", return_value=client_cm):
        return provider._get_viewer_model("examhash")


def test_get_viewer_model_non_json_body():
    with pytest.raises(RuntimeError, match="not JSON"):
        _get_viewer_model_with(json_exc=ValueError("Expecting value"))


def test_get_viewer_model_error_flag():
    with pytest.raises(ValueError, match="Viewer model error"):
        _get_viewer_model_with(json_data={"hasError": True, "errorMessage": "expired"})


def test_get_viewer_model_missing_exams():
    with pytest.raises(RuntimeError, match="missing exam entry"):
        _get_viewer_model_with(json_data={"hasError": False})


def test_get_viewer_model_non_object_exam():
    with pytest.raises(RuntimeError, match="expected object"):
        _get_viewer_model_with(json_data={"exams": ["not-a-dict"]})


def test_fetch_requires_access_code():
    provider = EasyRadiologyProvider()
    with pytest.raises(ValueError, match="access code is required"):
        provider.fetch("https://portal.easyradiology.net/View/abc", {})


def test_fetch_missing_download_link():
    provider = EasyRadiologyProvider()
    with (
        patch.object(provider, "_check_view_code", return_value="access-key"),
        patch.object(provider, "_get_viewer_model", return_value={"noLink": True}),
    ):
        with pytest.raises(RuntimeError, match="linkToERI"):
            provider.fetch("https://portal.easyradiology.net/View/abc", {"code": VALID_CODE})


def test_decrypt_aes_cbc_empty_ciphertext():
    with pytest.raises(ValueError, match="positive multiple of 16"):
        _decrypt_aes_cbc(b64encode(b"").decode(), "pw", "00" * 16, b64encode(b"\x00" * 16).decode())


def test_decrypt_aes_cbc_partial_block():
    with pytest.raises(ValueError, match="positive multiple of 16"):
        _decrypt_aes_cbc(b64encode(b"short").decode(), "pw", "00" * 16, b64encode(b"\x00" * 16).decode())
