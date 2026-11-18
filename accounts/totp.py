"""RFC 6238 TOTP (authenticator app) implementation using only the standard library."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify(secret, code, window=1):
    code = (code or "").strip().replace(" ", "")
    if not secret or not code.isdigit():
        return False
    now = int(time.time() // 30)
    return any(hmac.compare_digest(_code(secret, now + d), code) for d in range(-window, window + 1))


def provisioning_uri(secret, email, issuer="NACB"):
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}"
