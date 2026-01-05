"""
Security Headers Middleware
Enterprise-grade security header implementation for defense-in-depth.

Security Features:
- Content-Security-Policy (CSP) - Prevents XSS attacks
- X-Frame-Options - Prevents clickjacking
- X-Content-Type-Options - Prevents MIME sniffing
- Strict-Transport-Security (HSTS) - Enforces HTTPS
- X-XSS-Protection - Legacy XSS protection
- Referrer-Policy - Controls referrer information
- Permissions-Policy - Restricts browser features
"""
import os
from typing import Optional, List
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add comprehensive security headers to all responses.

    SECURITY NOTE:
    - CSP policy varies by environment (development vs production)
    - HSTS only enabled in production (requires HTTPS)
    - All headers follow OWASP recommendations
    """

    def __init__(self, app: ASGIApp, environment: str = "production"):
        super().__init__(app)
        self.environment = environment.lower()
        self.is_production = self.environment in ["production", "prod"]
        self.csp_policy = self._build_csp_policy()

    def _build_csp_policy(self) -> str:
        """
        Build Content-Security-Policy based on environment.

        Production: Strict policy, minimal permissions
        Development: More permissive for debugging tools
        """
        if self.is_production:
            # Strict production policy
            directives = [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline'",  # Allow inline styles for some UI frameworks
                "img-src 'self' data: blob:",
                "font-src 'self' data:",
                "connect-src 'self'",
                "media-src 'self'",
                "object-src 'none'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
                "upgrade-insecure-requests",
            ]
        else:
            # More permissive for development
            directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Allow for dev tools
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: blob: *",
                "font-src 'self' data: *",
                "connect-src 'self' ws: wss: http://localhost:* http://127.0.0.1:*",
                "media-src 'self' *",
                "object-src 'none'",
                "frame-ancestors 'self'",  # Allow same-origin framing for dev
                "base-uri 'self'",
                "form-action 'self'",
            ]

        return "; ".join(directives)

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # ==================== Content Security Policy ====================
        # Prevents XSS, data injection, and other code injection attacks
        response.headers["Content-Security-Policy"] = self.csp_policy

        # ==================== Clickjacking Protection ====================
        # Prevents the page from being embedded in frames/iframes
        response.headers["X-Frame-Options"] = "DENY"

        # ==================== MIME Sniffing Protection ====================
        # Prevents browser from MIME-sniffing response from declared content-type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # ==================== XSS Protection (Legacy) ====================
        # Enables XSS filter in legacy browsers (IE, older Chrome)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ==================== HTTPS Enforcement (Production Only) ====================
        if self.is_production:
            # Enforce HTTPS for 1 year, include subdomains, allow preload list
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # ==================== Referrer Policy ====================
        # Controls how much referrer information is sent
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ==================== Permissions Policy ====================
        # Restrict access to browser features (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        # ==================== Cache Control for Sensitive Data ====================
        # Prevent caching of sensitive API responses
        if request.url.path.startswith("/api/"):
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"

        # ==================== Remove Server Identification ====================
        # Hide server technology details
        if "server" in response.headers:
            del response.headers["server"]
        if "Server" in response.headers:
            del response.headers["Server"]

        # Remove X-Powered-By if present
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]

        return response


class CSPReportingMiddleware(BaseHTTPMiddleware):
    """
    CSP violation reporting endpoint middleware.

    Receives CSP violation reports from browsers and logs them.
    Enable this in production to monitor CSP violations.
    """

    def __init__(self, app: ASGIApp, report_uri: str = "/api/v1/security/csp-report"):
        super().__init__(app)
        self.report_uri = report_uri

    async def dispatch(self, request: Request, call_next):
        # Handle CSP report submissions
        if request.url.path == self.report_uri and request.method == "POST":
            import logging
            logger = logging.getLogger("security.csp")

            try:
                body = await request.body()
                logger.warning(
                    f"CSP Violation Report: {body.decode('utf-8', errors='replace')}"
                )
            except Exception as e:
                logger.error(f"Error processing CSP report: {e}")

            return Response(status_code=204)  # No content response

        return await call_next(request)


def get_cors_config(environment: str = "production", cors_origins: Optional[list] = None) -> dict:
    """
    Get CORS configuration based on environment.

    SECURITY NOTE:
    - Production: Strict origin whitelist
    - Development: More permissive for local development
    - Never use "*" for allow_origins in production
    """
    is_production = environment.lower() in ["production", "prod"]

    # Use provided cors_origins if available, otherwise use defaults
    if cors_origins:
        allowed_origins = cors_origins
    else:
        # Default origins
        if is_production:
            # In production, no default origins - must be configured
            allowed_origins = []
        else:
            # Development defaults
            allowed_origins = [
                "http://localhost:3000",
                "http://localhost:8501",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8501",
            ]

    return {
        "allow_origins": allowed_origins,
        "allow_credentials": True,  # Needed for cookies
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        "allow_headers": [
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "X-Requested-With",
            "Accept",
            "Accept-Language",
            "Origin",
        ],
        "expose_headers": [
            "X-Request-ID",
            "X-Process-Time-Ms",
            "Content-Disposition",
        ],
        "max_age": 600,  # Cache preflight for 10 minutes
    }
