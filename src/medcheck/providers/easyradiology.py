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
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx
from Crypto.Cipher import AES

from medcheck.core.context import DicomSeries
from medcheck.providers.base import DataProvider
from medcheck.providers.local import LocalProvider


def parse_access_code(code: str) -> tuple[str, str]:
    segments = code.split("-")
    if len(segments) < 3:
        raise ValueError(f"Invalid access code format: {code}. Expected at least 3 segments.")
    return "-".join(segments[:2]), "-".join(segments[2:])


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
        return bool(credentials.get("code") and credentials.get("dob"))

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
            raise ValueError(f"No exams found for code {view_code}")
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
        return data["exams"][0]

    def _download_and_decrypt(self, zip_url: str, access_key: str, exam_hash: str) -> list[DicomSeries]:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "exam.zip"
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                with client.stream("GET", zip_url) as resp:
                    resp.raise_for_status()
                    with open(zip_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)
            local = LocalProvider()
            return local.fetch(str(zip_path), {})
