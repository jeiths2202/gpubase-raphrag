"""
Linux-specific Chrome cookie decryption using GNOME Keyring and AES-128-CBC
"""
import hashlib
from typing import Optional

try:
    import secretstorage
    HAS_SECRETSTORAGE = True
except ImportError:
    HAS_SECRETSTORAGE = False

from Cryptodome.Cipher import AES
from Cryptodome.Protocol.KDF import PBKDF2

from ..exceptions import DecryptionError, UnsupportedOSError


def get_keyring_password() -> bytes:
    """
    Get Chrome encryption password from GNOME Keyring

    Returns:
        Chrome Safe Storage password from Keyring

    Raises:
        UnsupportedOSError: If secretstorage is not available
        DecryptionError: If Keyring access fails
    """
    if not HAS_SECRETSTORAGE:
        raise UnsupportedOSError("secretstorage module not available (install: pip install secretstorage)")

    try:
        # Connect to D-Bus session
        connection = secretstorage.dbus_init()

        # Get default collection (usually 'login')
        collection = secretstorage.get_default_collection(connection)

        # Search for Chrome Safe Storage
        items = collection.search_items({
            'application': 'chrome',
            'xdg:schema': 'chrome_libsecret_os_crypt_password_v2'
        })

        # Try alternative schema names
        if not items:
            items = collection.search_items({
                'application': 'chrome'
            })

        if not items:
            raise DecryptionError("Chrome Safe Storage not found in Keyring")

        # Get password from first matching item
        password = next(items).get_secret()

        connection.close()

        return password

    except StopIteration:
        raise DecryptionError("No Chrome password found in Keyring")
    except Exception as e:
        raise DecryptionError(f"Failed to access GNOME Keyring: {e}")


def derive_key(password: bytes, salt: bytes, iterations: int = 1) -> bytes:
    """
    Derive AES key using PBKDF2-HMAC-SHA1

    Args:
        password: Keyring password
        salt: Salt for key derivation (usually b'saltysalt')
        iterations: Number of iterations (default 1 for Linux Chrome)

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
    Decrypt Chrome cookie value on Linux

    Uses AES-128-CBC with PBKDF2-HMAC-SHA1 derived key

    Args:
        encrypted_value: Encrypted cookie value from database
        key: AES key (if None, will be derived from Keyring)

    Returns:
        Decrypted cookie value as string

    Raises:
        DecryptionError: If decryption fails
        UnsupportedOSError: If secretstorage is not available
    """
    if not HAS_SECRETSTORAGE:
        raise UnsupportedOSError("secretstorage module not available")

    if not encrypted_value:
        return ""

    try:
        # Chrome on Linux uses 'v10' or 'v11' prefix
        if encrypted_value[:3] not in (b'v10', b'v11'):
            # Try legacy format
            return encrypted_value.decode('utf-8')

        # Remove version prefix
        encrypted_value = encrypted_value[3:]

        # Get encryption key if not provided
        if key is None:
            password = get_keyring_password()
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
