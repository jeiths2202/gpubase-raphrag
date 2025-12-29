"""
Chrome Cookie Extractor - Main class for cross-platform cookie extraction
"""
import platform
from pathlib import Path
from typing import List, Optional

from .exceptions import (
    ChromeCookieError,
    CookieDBLockedError,
    UnsupportedOSError
)
from .models import Cookie
from .utils import (
    chrome_timestamp_to_datetime,
    copy_cookie_db,
    get_chrome_cookie_db_path,
    read_cookies_from_db
)


class ChromeCookieExtractor:
    """
    Cross-platform Chrome cookie extractor with OS-specific decryption
    """

    def __init__(self, profile: str = "Default"):
        """
        Initialize extractor for specified Chrome profile

        Args:
            profile: Chrome profile name (Default, Profile 1, etc.)
        """
        self.profile = profile
        self.system = platform.system()

        # Import OS-specific decryptor
        if self.system == "Windows":
            from .decryptors import windows
            self.decryptor = windows
            self.encryption_key = None
        elif self.system == "Darwin":  # macOS
            from .decryptors import macos
            self.decryptor = macos
            self.encryption_key = None
        elif self.system == "Linux":
            from .decryptors import linux
            self.decryptor = linux
            self.encryption_key = None
        else:
            raise UnsupportedOSError(f"Unsupported operating system: {self.system}")

    def _get_encryption_key(self) -> Optional[bytes]:
        """
        Get and cache encryption key for current OS

        Returns:
            Encryption key or None if not needed
        """
        if self.encryption_key is not None:
            return self.encryption_key

        try:
            if self.system == "Windows":
                self.encryption_key = self.decryptor.get_encryption_key()
            elif self.system == "Darwin":
                password = self.decryptor.get_keychain_password()
                salt = b'saltysalt'
                self.encryption_key = self.decryptor.derive_key(password, salt)
            elif self.system == "Linux":
                password = self.decryptor.get_keyring_password()
                salt = b'saltysalt'
                self.encryption_key = self.decryptor.derive_key(password, salt)

            return self.encryption_key

        except Exception as e:
            raise ChromeCookieError(f"Failed to get encryption key: {e}")

    def extract_cookies(self, domain: Optional[str] = None) -> List[Cookie]:
        """
        Extract and decrypt cookies from Chrome

        Args:
            domain: Optional domain filter (e.g., 'google.com')

        Returns:
            List of decrypted Cookie objects

        Raises:
            ChromeCookieError: If extraction fails
            CookieDBLockedError: If database is locked
        """
        try:
            # Get cookie database path
            cookie_db_path = get_chrome_cookie_db_path(self.profile)

            # Copy database to avoid lock issues
            temp_db_path = copy_cookie_db(cookie_db_path)

            try:
                # Read encrypted cookies from database
                raw_cookies = read_cookies_from_db(temp_db_path, domain)

                # Get encryption key once for all cookies
                key = self._get_encryption_key()

                # Decrypt cookies
                cookies = []
                for row in raw_cookies:
                    name, encrypted_value, host_key, path, expires_utc, is_secure, is_httponly = row

                    try:
                        # Decrypt cookie value
                        decrypted_value = self.decryptor.decrypt_cookie_value(encrypted_value, key)

                        # Convert Chrome timestamp
                        expires = chrome_timestamp_to_datetime(expires_utc)

                        # Create Cookie object
                        cookie = Cookie(
                            name=name,
                            value=decrypted_value,
                            domain=host_key,
                            path=path,
                            expires=expires,
                            is_secure=bool(is_secure),
                            is_httponly=bool(is_httponly)
                        )

                        cookies.append(cookie)

                    except Exception as e:
                        # Skip individual cookie errors, continue with others
                        print(f"Warning: Failed to decrypt cookie '{name}': {e}")
                        continue

                return cookies

            finally:
                # Clean up temporary database
                import shutil
                shutil.rmtree(temp_db_path.parent)

        except PermissionError as e:
            raise CookieDBLockedError(
                f"Cookie database is locked. Close Chrome and try again: {e}"
            )
        except Exception as e:
            raise ChromeCookieError(f"Failed to extract cookies: {e}")

    def extract_cookies_for_domain(self, domain: str) -> List[Cookie]:
        """
        Extract cookies for specific domain

        Args:
            domain: Target domain (e.g., 'tmaxsoft.com')

        Returns:
            List of cookies matching domain
        """
        return self.extract_cookies(domain=domain)

    def extract_cookies_as_dict(self, domain: Optional[str] = None) -> dict:
        """
        Extract cookies as dictionary format

        Args:
            domain: Optional domain filter

        Returns:
            Dictionary mapping cookie names to values
        """
        cookies = self.extract_cookies(domain)
        return {cookie.name: cookie.value for cookie in cookies}

    def extract_cookies_for_requests(self, domain: Optional[str] = None) -> dict:
        """
        Extract cookies in format compatible with requests.Session

        Args:
            domain: Optional domain filter

        Returns:
            Dictionary of cookies ready for requests.Session.cookies.set()
        """
        cookies = self.extract_cookies(domain)
        return {cookie.name: cookie.to_requests_cookie() for cookie in cookies}
