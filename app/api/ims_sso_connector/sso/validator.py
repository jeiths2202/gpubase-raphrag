"""
SSO Connection Validator
"""
from typing import Optional, Tuple
from urllib.parse import urlparse


class IMSSSOValidator:
    """
    Validator for IMS SSO connection parameters
    """

    @staticmethod
    def validate_url(ims_url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate IMS URL format

        Args:
            ims_url: URL to validate

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if not ims_url or not ims_url.strip():
            return False, "URL cannot be empty"

        try:
            parsed = urlparse(ims_url)

            if not parsed.scheme:
                return False, "URL must include protocol (http:// or https://)"

            if parsed.scheme not in ['http', 'https']:
                return False, "URL must use http or https protocol"

            if not parsed.netloc:
                return False, "Invalid URL format - no domain found"

            # Recommend HTTPS for security
            if parsed.scheme == 'http':
                # Warning but not error
                pass

            return True, None

        except Exception as e:
            return False, f"Invalid URL format: {str(e)}"

    @staticmethod
    def validate_chrome_profile(profile: str) -> Tuple[bool, Optional[str]]:
        """
        Validate Chrome profile name

        Args:
            profile: Profile name to validate

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if not profile or not profile.strip():
            return False, "Profile name cannot be empty"

        # Basic validation - Chrome profiles are alphanumeric with spaces
        if not all(c.isalnum() or c.isspace() for c in profile):
            return False, "Invalid profile name format"

        return True, None

    @staticmethod
    def validate_connection_params(
        ims_url: str,
        chrome_profile: str = "Default"
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate all connection parameters

        Args:
            ims_url: IMS URL
            chrome_profile: Chrome profile name

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        # Validate URL
        url_valid, url_error = IMSSSOValidator.validate_url(ims_url)
        if not url_valid:
            return False, f"URL validation failed: {url_error}"

        # Validate profile
        profile_valid, profile_error = IMSSSOValidator.validate_chrome_profile(chrome_profile)
        if not profile_valid:
            return False, f"Profile validation failed: {profile_error}"

        return True, None

    @staticmethod
    def sanitize_url(ims_url: str) -> str:
        """
        Sanitize and normalize IMS URL

        Args:
            ims_url: URL to sanitize

        Returns:
            Sanitized URL
        """
        # Strip whitespace
        ims_url = ims_url.strip()

        # Ensure HTTPS if no protocol specified
        if not ims_url.startswith(('http://', 'https://')):
            ims_url = f'https://{ims_url}'

        # Remove trailing slash
        ims_url = ims_url.rstrip('/')

        return ims_url
