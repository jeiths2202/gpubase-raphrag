"""
Utility functions for Chrome cookie extraction
"""
import os
import platform
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .exceptions import ChromeNotFoundError, ProfileNotFoundError


def chrome_timestamp_to_datetime(chrome_timestamp: int) -> Optional[datetime]:
    """
    Convert Chrome timestamp to Python datetime

    Chrome timestamps are microseconds since 1601-01-01 00:00:00 UTC
    """
    if chrome_timestamp == 0:
        return None

    # Chrome epoch: 1601-01-01
    # Unix epoch: 1970-01-01
    # Difference: 11644473600 seconds
    chrome_epoch = datetime(1601, 1, 1)
    return chrome_epoch + timedelta(microseconds=chrome_timestamp)


def get_chrome_cookie_db_path(profile: str = "Default") -> Path:
    """
    Get Chrome cookie database path based on OS

    Args:
        profile: Chrome profile name (Default, Profile 1, etc.)

    Returns:
        Path to Chrome Cookies database

    Raises:
        ChromeNotFoundError: If Chrome is not installed
        ProfileNotFoundError: If specified profile doesn't exist
    """
    system = platform.system()

    if system == "Windows":
        base_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    elif system == "Darwin":  # macOS
        base_path = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    elif system == "Linux":
        base_path = Path.home() / ".config" / "google-chrome"
    else:
        raise ChromeNotFoundError(f"Unsupported operating system: {system}")

    if not base_path.exists():
        raise ChromeNotFoundError(f"Chrome installation not found at {base_path}")

    profile_path = base_path / profile
    if not profile_path.exists():
        raise ProfileNotFoundError(f"Chrome profile '{profile}' not found at {profile_path}")

    cookie_db = profile_path / "Cookies"
    if not cookie_db.exists():
        # Try Network/Cookies for newer Chrome versions
        cookie_db = profile_path / "Network" / "Cookies"
        if not cookie_db.exists():
            raise ProfileNotFoundError(f"Cookie database not found in profile '{profile}'")

    return cookie_db


def get_chrome_local_state_path() -> Path:
    """
    Get Chrome Local State file path (contains encryption key on Windows)

    Returns:
        Path to Local State file

    Raises:
        ChromeNotFoundError: If Chrome is not installed
    """
    system = platform.system()

    if system == "Windows":
        base_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    elif system == "Darwin":
        base_path = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    elif system == "Linux":
        base_path = Path.home() / ".config" / "google-chrome"
    else:
        raise ChromeNotFoundError(f"Unsupported operating system: {system}")

    local_state = base_path / "Local State"
    if not local_state.exists():
        raise ChromeNotFoundError(f"Chrome Local State not found at {local_state}")

    return local_state


def copy_cookie_db(cookie_db_path: Path) -> Path:
    """
    Copy Chrome cookie database to temp location

    Chrome locks the database when running, so we copy it to read

    Args:
        cookie_db_path: Path to Chrome Cookies database

    Returns:
        Path to temporary copy of database
    """
    temp_dir = tempfile.mkdtemp(prefix="chrome_cookies_")
    temp_db = Path(temp_dir) / "Cookies"
    shutil.copy2(cookie_db_path, temp_db)
    return temp_db


def read_cookies_from_db(db_path: Path, domain: Optional[str] = None) -> list:
    """
    Read cookies from Chrome SQLite database

    Args:
        db_path: Path to Cookies database
        domain: Optional domain filter (e.g., '.google.com')

    Returns:
        List of raw cookie rows from database
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    if domain:
        query = """
            SELECT name, encrypted_value, host_key, path, expires_utc, is_secure, is_httponly
            FROM cookies
            WHERE host_key LIKE ?
        """
        cursor.execute(query, (f'%{domain}%',))
    else:
        query = """
            SELECT name, encrypted_value, host_key, path, expires_utc, is_secure, is_httponly
            FROM cookies
        """
        cursor.execute(query)

    cookies = cursor.fetchall()
    conn.close()

    return cookies
