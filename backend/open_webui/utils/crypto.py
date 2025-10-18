from typing import Optional
import os

from cryptography.fernet import Fernet, InvalidToken  # pip install cryptography

_ENC_KEY = os.getenv("ENCRYPTION_KEY")  # 32-byte urlsafe base64

def _fernet() -> Optional[Fernet]:
    if not _ENC_KEY:
        return None
    try:
        return Fernet(_ENC_KEY.encode() if not _ENC_KEY.startswith(("gAAAA",)) else _ENC_KEY)  # be lenient
    except Exception:
        return None

def encrypt_str(plain: str) -> str:
    f = _fernet()
    if not f:
        # fallback: store as-is (not ideal, but don't crash)
        return plain
    return f.encrypt(plain.encode()).decode()

def decrypt_str(cipher: str) -> str:
    f = _fernet()
    if not f:
        return cipher  # best effort if key missing (won't be readable if actually encrypted)
    try:
        return f.decrypt(cipher.encode()).decode()
    except InvalidToken:
        # value might already be plaintext (older rows)
        return cipher
