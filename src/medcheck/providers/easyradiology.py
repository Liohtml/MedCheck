"""easyRadiology portal provider.

Reverse-engineered protocol for fetching DICOM data from easyRadiology portals.

Credits:
- easyRadiology AG (https://www.easyradiology.net) - portal software
- Encryption uses scrypt (RFC 7914) + AES-CBC (FIPS 197)
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from base64 import b64decode
from collections.abc import Iterable
from pathlib import Path
from typing import Any, BinaryIO, ClassVar
from urllib.parse import urlparse

import httpx

# Uses pycryptodome (the maintained pycrypto fork), NOT the abandoned pycrypto.
# Bandit's B413 fires on the shared "Crypto" namespace and cannot tell the two
# apart, so the suppression is required even though the library is the safe one.
from Crypto.Cipher import AES  # nosec B413

from medcheck.core.config import Settings
from medcheck.core.context import DicomSeries
from medcheck.providers.base import DataProvider
from medcheck.providers.local import LocalProvider


def parse_access_code(code: str) -> tuple[str, str]:
    segments = code.split("-")
    if len(segments) < 3:
        # Never echo the credential itself into the exception (it can leak to logs).
        raise ValueError(
            f"Invalid access code format: expected at least 3 dash-separated segments, got {len(segments)}."
        )
    return "-".join(segments[:2]), "-".join(segments[2:])


# Hosts the encrypted exam ZIP (linkToERI) is allowed to be downloaded from.
# Restricting this prevents SSRF if a spoofed/MITM portal response points the
# download at localhost, RFC 1918 ranges, or cloud metadata endpoints.
_ALLOWED_DOWNLOAD_SUFFIXES = (".easyradiology.net", ".easyradiology.de")
_ALLOWED_DOWNLOAD_HOSTS = {"easyradiology.net", "easyradiology.de"}


def _validate_download_url(url: str) -> None:
    """Reject download URLs that are not HTTPS on a trusted easyRadiology host."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Unsafe download URL scheme: {parsed.scheme!r} (expected https)")
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_DOWNLOAD_HOSTS and not host.endswith(_ALLOWED_DOWNLOAD_SUFFIXES):
        raise ValueError(f"Untrusted download host: {host!r}")


# Default hard cap on the exam ZIP download. A tampered/compromised portal response
# could otherwise stream an unbounded body and exhaust disk. 2 GiB is comfortably
# above any real exam while still bounding the damage. Overridable per-deployment
# via Settings.max_download_bytes (MEDCHECK_MAX_DOWNLOAD_BYTES).
_MAX_DOWNLOAD_BYTES: int = 2 * 1024 * 1024 * 1024


def _check_content_length(content_length: str | None, max_bytes: int) -> None:
    """Reject up front if the server advertises a body larger than *max_bytes*.

    An absent, unparsable, or negative length is left to the streamed-byte cap in
    ``_write_capped`` rather than trusted here.
    """
    if content_length is None:
        return
    try:
        declared = int(content_length)
    except ValueError:
        return
    if declared > max_bytes:
        raise ValueError(f"Download too large: {declared} bytes exceeds the {max_bytes}-byte limit")


def _write_capped(chunks: Iterable[bytes], dest: BinaryIO, max_bytes: int) -> int:
    """Write *chunks* to *dest*, aborting if more than *max_bytes* are written.

    Guards against servers that omit/understate Content-Length and then stream an
    oversized body. Returns the number of bytes written.
    """
    written = 0
    for chunk in chunks:
        written += len(chunk)
        if written > max_bytes:
            raise ValueError(f"Download exceeded the {max_bytes}-byte limit")
        dest.write(chunk)
    return written


def _scrypt_derive(password: str, salt: bytes, n: int = 16384, r: int = 8, p: int = 1, dklen: int = 32) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen)


def _scrypt_key_verification(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    key = _scrypt_derive(password, salt)
    return f"scrypt2:16384:8:1:0:32:{salt_hex}:{key.hex()}"


def _decrypt_aes_cbc(ciphertext_b64: str, password: str, salt_hex: str, iv_b64: str) -> bytes:
    salt = bytes.fromhex(salt_hex)
    iv = b64decode(iv_b64)
    ct = b64decode(ciphertext_b64)
    key = _scrypt_derive(password, salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    dec = cipher.decrypt(ct)
    pad = dec[-1]
    if 0 < pad <= 16 and all(b == pad for b in dec[-pad:]):
        return dec[:-pad]
    raise ValueError("AES-CBC decryption failed: invalid PKCS7 padding")


class EasyRadiologyProvider(DataProvider):
    name = "easyradiology"
    url_patterns: ClassVar[list[str]] = ["easyradiology.net", "easyradiology.de"]
    BASE_URL = "https://portal.easyradiology.net"

    def authenticate(self, credentials: dict[str, str]) -> bool:
        # Only the access code authenticates this client: it derives the scrypt
        # key verification sent to CheckViewCode. Date of birth is collected by
        # the portal UI but is NOT used (nor verified) by this reverse-engineered
        # flow, so we must not gate on it and imply a protection that isn't there.
        return bool(credentials.get("code"))

    def fetch(self, target: str, credentials: dict[str, str]) -> list[DicomSeries]:
        code = credentials["code"]
        exam_hash = self._extract_exam_hash(target)
        access_key = self._check_view_code(code, exam_hash)
        viewer_model = self._get_viewer_model(exam_hash)
        zip_url = viewer_model["linkToERI"]
        return self._download_and_decrypt(zip_url, access_key, exam_hash)

    def _extract_exam_hash(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed.path.strip("/").split("/")[-1]

    def _check_view_code(self, code: str, exam_hash: str) -> str:
        view_code, _ = parse_access_code(code)
        salt_hex = view_code.encode("ascii").hex()
        key_verification = _scrypt_key_verification(code, salt_hex)
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.BASE_URL}/api/viewexam/CheckViewCode",
                json={"ViewCodeName": view_code, "KeyVerification": key_verification, "WithDeferred": True},
            )
            resp.raise_for_status()
            data = resp.json()
        if not data.get("exams"):
            raise ValueError("No exams found for the provided access code")
        exam = data["exams"][0]
        enc = json.loads(exam["encryptedAccessKey"])
        access_key_bytes = _decrypt_aes_cbc(enc["CipherOutputText"], code, enc["Salt"], enc["AesRijndaelIv"])
        return access_key_bytes.decode("utf-8")

    def _get_viewer_model(self, exam_hash: str) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.BASE_URL}/api/viewexam/GetViewerModel", json=[{"ExamHash": exam_hash}])
            resp.raise_for_status()
            data = resp.json()
        if data.get("hasError"):
            raise ValueError(f"Viewer model error: {data.get('errorMessage', '')}")
        result: dict[str, Any] = data["exams"][0]
        return result

    def _download_and_decrypt(self, zip_url: str, access_key: str, exam_hash: str) -> list[DicomSeries]:
        # Validate before fetching to guard against SSRF via a tampered linkToERI.
        _validate_download_url(zip_url)
        max_bytes = Settings().max_download_bytes
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "exam.zip"
            # Redirects are disabled: a 30x bounce could escape the host allowlist.
            with httpx.Client(timeout=120.0, follow_redirects=False) as client:
                with client.stream("GET", zip_url) as resp:
                    resp.raise_for_status()
                    # Reject early on an oversized advertised length, then enforce the
                    # cap on the actual streamed bytes in case the header lies/is absent.
                    _check_content_length(resp.headers.get("Content-Length"), max_bytes)
                    with open(zip_path, "wb") as f:
                        _write_capped(resp.iter_bytes(chunk_size=8192), f, max_bytes)
            local = LocalProvider()
            return local.fetch(str(zip_path), {})
