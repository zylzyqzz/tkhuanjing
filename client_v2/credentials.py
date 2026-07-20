from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def protect(value: str) -> str:
    if os.name != "nt":
        return "dev:" + base64.b64encode(value.encode()).decode()
    source, keepalive = _blob(value.encode())
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "VD Nexus", None, None, None, 0, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return "dpapi:" + base64.b64encode(ctypes.string_at(output.pbData, output.cbData)).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def unprotect(value: str) -> str:
    if value.startswith("dev:"):
        return base64.b64decode(value[4:]).decode()
    if not value.startswith("dpapi:") or os.name != "nt":
        return ""
    source, keepalive = _blob(base64.b64decode(value[6:]))
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        return ""
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


class CredentialStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return {key: unprotect(value) for key, value in raw.items()}
        except (OSError, ValueError, TypeError):
            return {}

    def save(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({key: protect(value) for key, value in values.items()}), encoding="utf-8")
        os.chmod(temp, 0o600)
        os.replace(temp, self.path)

    def clear(self, *keys: str) -> None:
        values = self.load()
        for key in keys:
            values.pop(key, None)
        self.save(values)
