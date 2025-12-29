"""
Windows-specific Chrome cookie decryption using DPAPI and AES-256-GCM
"""
import base64
import json
from pathlib import Path
from typing import Optional

try:
    import win32crypt
    HAS_WIN32CRYPT = True
except ImportError:
    HAS_WIN32CRYPT = False

from Cryptodome.Cipher import AES

from ..exceptions import DecryptionError, UnsupportedOSError
from ..utils import get_chrome_local_state_path


def get_encryption_key() -> bytes:
    """
    Get Chrome encryption key from Local State file

    Returns:
        Decrypted AES master key

    Raises:
        UnsupportedOSError: If win32crypt is not available
        DecryptionError: If key extraction fails
    """
    if not HAS_WIN32CRYPT:
        raise UnsupportedOSError("win32crypt module not available (Windows only)")

    try:
        local_state_path = get_chrome_local_state_path()

        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)

        encrypted_key = local_state['os_crypt']['encrypted_key']

        # Decode from base64
        encrypted_key = base64.b64decode(encrypted_key)

        # Remove DPAPI prefix 'DPAPI'
        encrypted_key = encrypted_key[5:]

        # Decrypt using DPAPI
        decrypted_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]

        return decrypted_key

    except KeyError as e:
        raise DecryptionError(f"Encryption key not found in Local State: {e}")
    except Exception as e:
        raise DecryptionError(f"Failed to get encryption key: {e}")


def decrypt_cookie_value(encrypted_value: bytes, key: Optional[bytes] = None) -> str:
    """
    Decrypt Chrome cookie value on Windows

    Supports both v10/v11 (AES-256-GCM) and legacy (DPAPI) encryption

    Args:
        encrypted_value: Encrypted cookie value from database
        key: AES master key (if None, will be fetched)

    Returns:
        Decrypted cookie value as string

    Raises:
        DecryptionError: If decryption fails
        UnsupportedOSError: If running on non-Windows platform
    """
    if not HAS_WIN32CRYPT:
        raise UnsupportedOSError("win32crypt module not available (Windows only)")

    if not encrypted_value:
        return ""

    try:
        # Check for v10/v11 encryption (starts with 'v10' or 'v11')
        if encrypted_value[:3] == b'v10' or encrypted_value[:3] == b'v11':
            # Get encryption key if not provided
            if key is None:
                key = get_encryption_key()

            # Extract components
            # v10/v11 format: version (3 bytes) + nonce (12 bytes) + ciphertext + tag (16 bytes)
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:-16]
            tag = encrypted_value[-16:]

            # Decrypt using AES-256-GCM
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted_value = cipher.decrypt_and_verify(ciphertext, tag)

            return decrypted_value.decode('utf-8')

        else:
            # Legacy DPAPI encryption
            decrypted_value = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1]
            return decrypted_value.decode('utf-8')

    except Exception as e:
        raise DecryptionError(f"Failed to decrypt cookie value: {e}")
