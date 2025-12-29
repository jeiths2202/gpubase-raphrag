"""
macOS-specific Chrome cookie decryption using Keychain and AES-128-CBC
"""
import hashlib
import subprocess
from typing import Optional

from Cryptodome.Cipher import AES
from Cryptodome.Protocol.KDF import PBKDF2

from ..exceptions import DecryptionError, UnsupportedOSError


def get_keychain_password() -> bytes:
    """
    Get Chrome encryption password from macOS Keychain

    Returns:
        Chrome Safe Storage password from Keychain

    Raises:
        UnsupportedOSError: If not running on macOS
        DecryptionError: If Keychain access fails
    """
    try:
        # Use security command to access Keychain
        command = [
            'security',
            'find-generic-password',
            '-w',  # Output password only
            '-s', 'Chrome Safe Storage',  # Service name
            '-a', 'Chrome'  # Account name
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )

        password = result.stdout.strip()

        if not password:
            raise DecryptionError("Empty password returned from Keychain")

        return password.encode('utf-8')

    except subprocess.CalledProcessError as e:
        raise DecryptionError(f"Failed to access Keychain: {e.stderr}")
    except Exception as e:
        raise DecryptionError(f"Keychain access error: {e}")


def derive_key(password: bytes, salt: bytes, iterations: int = 1003) -> bytes:
    """
    Derive AES key using PBKDF2-HMAC-SHA1

    Args:
        password: Keychain password
        salt: Salt for key derivation (usually b'saltysalt')
        iterations: Number of iterations (default 1003 for Chrome)

    Returns:
        16-byte AES-128 key
    """
    key = PBKDF2(
        password,
        salt,
        dkLen=16,  # AES-128 key length
        count=iterations,
        hmac_hash_module=hashlib.sha1
    )
    return key


def decrypt_cookie_value(encrypted_value: bytes, key: Optional[bytes] = None) -> str:
    """
    Decrypt Chrome cookie value on macOS

    Uses AES-128-CBC with PBKDF2-HMAC-SHA1 derived key

    Args:
        encrypted_value: Encrypted cookie value from database
        key: AES key (if None, will be derived from Keychain)

    Returns:
        Decrypted cookie value as string

    Raises:
        DecryptionError: If decryption fails
        UnsupportedOSError: If not running on macOS
    """
    if not encrypted_value:
        return ""

    try:
        # Chrome on macOS uses 'v10' prefix
        if encrypted_value[:3] != b'v10':
            # Try legacy format (unlikely on modern Chrome)
            return encrypted_value.decode('utf-8')

        # Remove 'v10' prefix
        encrypted_value = encrypted_value[3:]

        # Get encryption key if not provided
        if key is None:
            password = get_keychain_password()
            salt = b'saltysalt'
            key = derive_key(password, salt)

        # Extract IV (first 16 bytes) and ciphertext
        iv = b' ' * 16  # Chrome uses 16 spaces as IV
        ciphertext = encrypted_value

        # Decrypt using AES-128-CBC
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        decrypted_value = cipher.decrypt(ciphertext)

        # Remove PKCS7 padding
        padding_length = decrypted_value[-1]
        if isinstance(padding_length, int):
            decrypted_value = decrypted_value[:-padding_length]
        else:
            decrypted_value = decrypted_value[:-ord(padding_length)]

        return decrypted_value.decode('utf-8')

    except Exception as e:
        raise DecryptionError(f"Failed to decrypt cookie value: {e}")
