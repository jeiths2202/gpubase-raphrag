"""
SSO Connection Service using Chrome cookies
"""
import requests
from typing import Optional, Tuple
from urllib.parse import urlparse

from ..chrome_cookie_extractor.extractor import ChromeCookieExtractor
from ..chrome_cookie_extractor.exceptions import ChromeCookieError


class IMSSSOService:
    """
    IMS SSO Service for cookie-based authentication
    """

    def __init__(self):
        self.session: Optional[requests.Session] = None
        self.ims_url: Optional[str] = None
        self.user_info: Optional[dict] = None

    def connect(
        self,
        ims_url: str,
        chrome_profile: str = "Default",
        validation_endpoint: str = "/api/v1/me"
    ) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Connect to IMS system using Chrome cookies

        Args:
            ims_url: IMS system URL (e.g., https://ims.tmaxsoft.com)
            chrome_profile: Chrome profile name to extract cookies from
            validation_endpoint: API endpoint to validate authentication

        Returns:
            Tuple of (success: bool, error_message: Optional[str], user_info: Optional[dict])
        """
        try:
            # Parse domain from URL
            parsed_url = urlparse(ims_url)
            domain = parsed_url.netloc

            # Extract cookies from Chrome
            extractor = ChromeCookieExtractor(profile=chrome_profile)
            cookies = extractor.extract_cookies_for_domain(domain)

            if not cookies:
                return False, f"No cookies found for domain: {domain}", None

            # Create authenticated session
            self.session = requests.Session()
            self.ims_url = ims_url

            # Add cookies to session
            for cookie in cookies:
                self.session.cookies.set(
                    name=cookie.name,
                    value=cookie.value,
                    domain=cookie.domain,
                    path=cookie.path,
                    secure=cookie.is_secure,
                    rest={'HttpOnly': cookie.is_httponly}
                )

            # Validate connection
            success, error, user_info = self._validate_connection(validation_endpoint)

            if success:
                self.user_info = user_info
                return True, None, user_info
            else:
                self.session = None
                return False, error, None

        except ChromeCookieError as e:
            return False, f"Cookie extraction failed: {str(e)}", None
        except Exception as e:
            return False, f"Connection failed: {str(e)}", None

    def _validate_connection(
        self,
        validation_endpoint: str
    ) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Validate SSO connection by calling protected endpoint

        Args:
            validation_endpoint: API endpoint to test authentication

        Returns:
            Tuple of (success: bool, error_message: Optional[str], user_info: Optional[dict])
        """
        if not self.session or not self.ims_url:
            return False, "No active session", None

        try:
            # Call validation endpoint
            url = f"{self.ims_url.rstrip('/')}{validation_endpoint}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                try:
                    user_info = response.json()
                    return True, None, user_info
                except Exception:
                    # Endpoint responded successfully but no JSON
                    return True, None, {"authenticated": True}

            elif response.status_code == 401:
                return False, "Authentication failed - cookies may be expired", None

            elif response.status_code == 404:
                # Endpoint not found, try alternative
                return self._try_alternative_validation()

            else:
                return False, f"Validation failed with status {response.status_code}", None

        except requests.exceptions.Timeout:
            return False, "Connection timeout", None
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to IMS system", None
        except Exception as e:
            return False, f"Validation error: {str(e)}", None

    def _try_alternative_validation(self) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Try alternative validation endpoints if primary fails

        Returns:
            Tuple of (success: bool, error_message: Optional[str], user_info: Optional[dict])
        """
        alternative_endpoints = [
            "/api/user/profile",
            "/api/auth/me",
            "/api/me",
            "/"  # Root endpoint as last resort
        ]

        for endpoint in alternative_endpoints:
            try:
                url = f"{self.ims_url.rstrip('/')}{endpoint}"
                response = self.session.get(url, timeout=5)

                if response.status_code == 200:
                    return True, None, {"authenticated": True, "endpoint": endpoint}

            except Exception:
                continue

        return False, "No valid authentication endpoint found", None

    def make_request(
        self,
        endpoint: str,
        method: str = "GET",
        **kwargs
    ) -> Optional[requests.Response]:
        """
        Make authenticated request to IMS system

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            **kwargs: Additional arguments for requests

        Returns:
            Response object or None if no session
        """
        if not self.session or not self.ims_url:
            return None

        url = f"{self.ims_url.rstrip('/')}{endpoint}"

        try:
            response = self.session.request(method, url, **kwargs)
            return response
        except Exception as e:
            print(f"Request error: {e}")
            return None

    def disconnect(self):
        """
        Disconnect SSO session
        """
        if self.session:
            self.session.close()
            self.session = None
            self.ims_url = None
            self.user_info = None

    def is_connected(self) -> bool:
        """
        Check if SSO session is active

        Returns:
            True if connected, False otherwise
        """
        return self.session is not None and self.ims_url is not None
