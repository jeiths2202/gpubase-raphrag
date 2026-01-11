"""
Authentication manager for CLI Agent

Handles login, token storage, and session management.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta

try:
    import httpx
except ImportError:
    httpx = None


class AuthManager:
    """Manages authentication tokens and session"""

    TOKEN_FILE = ".kms_cli_token"

    def __init__(self, config):
        self.config = config
        self.access_token: Optional[str] = None
        self.refresh_token_value: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.user_info: Optional[Dict] = None

        # IMS session info
        self.ims_credentials: Optional[Dict] = None
        self.ims_validated: bool = False

        # Load saved token
        self._load_token()

    def _get_token_path(self) -> Path:
        """Get path to token file"""
        # Store in user's home directory
        return Path.home() / self.TOKEN_FILE

    def _load_token(self):
        """Load saved token from file"""
        token_path = self._get_token_path()
        if token_path.exists():
            try:
                with open(token_path, "r") as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token_value = data.get("refresh_token")
                    if data.get("expiry"):
                        self.token_expiry = datetime.fromisoformat(data["expiry"])
                    self.user_info = data.get("user_info")
            except (json.JSONDecodeError, IOError):
                pass

    def _save_token(self):
        """Save token to file"""
        token_path = self._get_token_path()
        try:
            data = {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token_value,
                "expiry": self.token_expiry.isoformat() if self.token_expiry else None,
                "user_info": self.user_info,
            }
            with open(token_path, "w") as f:
                json.dump(data, f)
            # Set restrictive permissions on Unix
            if os.name != "nt":
                os.chmod(token_path, 0o600)
        except IOError:
            pass

    def clear_token(self):
        """Clear saved token"""
        self.access_token = None
        self.refresh_token_value = None
        self.token_expiry = None
        self.user_info = None

        token_path = self._get_token_path()
        if token_path.exists():
            try:
                token_path.unlink()
            except IOError:
                pass

    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        if not self.access_token:
            return False

        # Check if token is expired
        if self.token_expiry and datetime.now() >= self.token_expiry:
            return False

        return True

    def login(self, username: str, password: str) -> bool:
        """Login with username and password"""
        if not httpx:
            return False

        url = f"{self.config.api_url}/auth/login"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    url,
                    json={
                        "username": username,
                        "password": password,
                    },
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    response_data = response.json()
                    # Handle wrapped response: {"success": true, "data": {...}}
                    if response_data.get("success") and "data" in response_data:
                        data = response_data["data"]
                    else:
                        data = response_data

                    self.access_token = data.get("access_token")
                    self.refresh_token_value = data.get("refresh_token")

                    # Set expiry (default: 30 minutes)
                    expires_in = data.get("expires_in", 1800)
                    self.token_expiry = datetime.now() + timedelta(seconds=expires_in)

                    # Get user info
                    self.user_info = data.get("user", {})

                    self._save_token()
                    return True

                return False

        except Exception:
            return False

    def refresh_token(self) -> bool:
        """Refresh the access token"""
        if not httpx or not self.refresh_token_value:
            return False

        url = f"{self.config.api_url}/auth/refresh"

        try:
            with httpx.Client(timeout=30.0) as client:
                # Try cookie-based refresh first
                response = client.post(
                    url,
                    cookies={"refresh_token": self.refresh_token_value} if self.refresh_token_value else None,
                    headers=self.get_headers() if self.access_token else None
                )

                if response.status_code == 200:
                    data = response.json()
                    self.access_token = data.get("access_token")

                    if data.get("refresh_token"):
                        self.refresh_token_value = data["refresh_token"]

                    expires_in = data.get("expires_in", 1800)
                    self.token_expiry = datetime.now() + timedelta(seconds=expires_in)

                    self._save_token()
                    return True

                return False

        except Exception:
            return False

    def get_headers(self) -> Optional[Dict[str, str]]:
        """Get authorization headers"""
        if not self.access_token:
            return None

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def get_user_display(self) -> str:
        """Get user display name"""
        if not self.user_info:
            return "Unknown"

        return self.user_info.get("username") or self.user_info.get("email") or "User"

    # =========================================================================
    # IMS Credentials Management
    # =========================================================================

    def check_ims_credentials(self) -> tuple[bool, Optional[Dict]]:
        """
        Check if IMS credentials exist and are validated.

        Returns:
            (is_valid, credentials_info) tuple
        """
        if not httpx or not self.access_token:
            return False, None

        url = f"{self.config.api_url}/ims-crawler/ims-credentials/"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=self.get_headers())

                if response.status_code == 200:
                    response_data = response.json()
                    # Handle wrapped response
                    if response_data.get("success") and "data" in response_data:
                        data = response_data["data"]
                    else:
                        data = response_data

                    self.ims_credentials = data
                    self.ims_validated = data.get("is_validated", False)

                    return self.ims_validated, data

                elif response.status_code == 404:
                    # Credentials not found
                    self.ims_credentials = None
                    self.ims_validated = False
                    return False, None

                return False, None

        except Exception:
            return False, None

    def ims_login(self, username: str, password: str, ims_url: str = "https://ims.tmaxsoft.com") -> tuple[bool, str]:
        """
        Create/update IMS credentials and validate.

        Returns:
            (success, message) tuple
        """
        if not httpx or not self.access_token:
            return False, "Not authenticated"

        url = f"{self.config.api_url}/ims-crawler/ims-credentials/"

        try:
            with httpx.Client(timeout=60.0) as client:
                # Create/update credentials
                response = client.post(
                    url,
                    json={
                        "ims_url": ims_url,
                        "username": username,
                        "password": password,
                    },
                    headers=self.get_headers()
                )

                if response.status_code in (200, 201):
                    response_data = response.json()
                    if response_data.get("success") and "data" in response_data:
                        data = response_data["data"]
                    else:
                        data = response_data

                    self.ims_credentials = data

                    # Now validate the credentials
                    return self.validate_ims_credentials()

                else:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    return False, error_msg

        except Exception as e:
            return False, str(e)

    def validate_ims_credentials(self) -> tuple[bool, str]:
        """
        Validate stored IMS credentials.

        Returns:
            (success, message) tuple
        """
        if not httpx or not self.access_token:
            return False, "Not authenticated"

        url = f"{self.config.api_url}/ims-crawler/ims-credentials/validate"

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, headers=self.get_headers())

                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get("success") and "data" in response_data:
                        data = response_data["data"]
                    else:
                        data = response_data

                    is_valid = data.get("is_valid", False)
                    message = data.get("message", "")

                    self.ims_validated = is_valid
                    return is_valid, message

                else:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Validation failed")
                    self.ims_validated = False
                    return False, error_msg

        except Exception as e:
            self.ims_validated = False
            return False, str(e)

    def ims_logout(self) -> tuple[bool, str]:
        """
        Delete IMS credentials (logout).

        Returns:
            (success, message) tuple
        """
        if not httpx or not self.access_token:
            return False, "Not authenticated"

        url = f"{self.config.api_url}/ims-crawler/ims-credentials/"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.delete(url, headers=self.get_headers())

                if response.status_code == 204:
                    self.ims_credentials = None
                    self.ims_validated = False
                    return True, "IMS credentials deleted"

                return False, "Failed to delete credentials"

        except Exception as e:
            return False, str(e)

    def is_ims_authenticated(self) -> bool:
        """Check if IMS is authenticated"""
        return self.ims_validated and self.ims_credentials is not None
