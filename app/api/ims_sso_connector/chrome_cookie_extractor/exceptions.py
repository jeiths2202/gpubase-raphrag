"""
Custom exceptions for Chrome cookie extraction
"""


class ChromeCookieError(Exception):
    """Base exception for Chrome cookie extraction errors"""
    pass


class ChromeNotFoundError(ChromeCookieError):
    """Chrome installation not found"""
    pass


class ProfileNotFoundError(ChromeCookieError):
    """Chrome profile not found"""
    pass


class CookieDBLockedError(ChromeCookieError):
    """Cookie database is locked by Chrome"""
    pass


class DecryptionError(ChromeCookieError):
    """Cookie decryption failed"""
    pass


class PermissionError(ChromeCookieError):
    """Permission denied accessing Chrome data"""
    pass


class UnsupportedOSError(ChromeCookieError):
    """Operating system not supported"""
    pass
