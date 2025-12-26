"""
Security Hardening Validation Tests
Enterprise-grade security test suite for validating security remediation.

Tests verify:
1. No DEBUG auth bypass
2. No hardcoded secrets
3. Security headers present
4. HttpOnly cookies configured
5. CORS restrictions in place
"""
import os
import pytest
import subprocess
from pathlib import Path


def read_file_utf8(file_path: Path) -> str:
    """Read file with UTF-8 encoding"""
    return file_path.read_text(encoding='utf-8')


class TestNoHardcodedSecrets:
    """Verify no hardcoded secrets in codebase"""

    @pytest.fixture
    def project_root(self):
        """Get project root directory"""
        return Path(__file__).parent.parent.parent

    def test_no_hardcoded_jwt_secrets(self, project_root):
        """Verify no hardcoded JWT secret defaults in API code"""
        # Check config.py - JWT_SECRET_KEY should be required (no default)
        config_file = project_root / "app" / "api" / "core" / "config.py"
        content = read_file_utf8(config_file)

        # Should have "..." (required) instead of a default value
        assert 'JWT_SECRET_KEY: str = Field(' in content
        assert '...' in content  # Required field marker

    def test_no_hardcoded_encryption_keys(self, project_root):
        """Verify no hardcoded encryption key defaults in security_service.py"""
        security_file = project_root / "app" / "api" / "services" / "security_service.py"
        content = read_file_utf8(security_file)

        # Should not have default values for encryption keys
        assert 'os.environ.get("ENCRYPTION_MASTER_KEY")' in content
        assert 'os.environ.get("ENCRYPTION_SALT")' in content
        # Should NOT have fallback defaults
        assert '"default-dev-key"' not in content.replace('KNOWN_INSECURE', '')

    def test_no_hardcoded_admin_password(self, project_root):
        """Verify no hardcoded admin password hash in deps.py"""
        deps_file = project_root / "app" / "api" / "core" / "deps.py"
        content = read_file_utf8(deps_file)

        # SHA256("admin") hash should NOT be present
        admin_hash = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"
        assert admin_hash not in content

    def test_env_example_has_empty_secrets(self, project_root):
        """Verify .env.example has empty values for secrets"""
        env_file = project_root / ".env.example"
        content = read_file_utf8(env_file)

        # These should have empty values (just the key, no value)
        lines = content.split('\n')
        jwt_line = [l for l in lines if l.startswith('JWT_SECRET_KEY=')][0]
        assert jwt_line == 'JWT_SECRET_KEY=' or jwt_line == 'JWT_SECRET_KEY=""'

        enc_line = [l for l in lines if l.startswith('ENCRYPTION_MASTER_KEY=')][0]
        assert enc_line == 'ENCRYPTION_MASTER_KEY=' or enc_line == 'ENCRYPTION_MASTER_KEY=""'


class TestNoDebugAuthBypass:
    """Verify no DEBUG mode authentication bypass"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent

    def test_no_debug_bypass_in_deps(self, project_root):
        """Verify no DEBUG bypass in deps.py get_current_user"""
        deps_file = project_root / "app" / "api" / "core" / "deps.py"
        content = read_file_utf8(deps_file)

        # Should NOT have api_settings.DEBUG check in get_current_user that returns mock user
        # Look for the pattern of DEBUG returning dev_user
        assert 'if api_settings.DEBUG:' not in content

    def test_no_dev_user_privilege_bypass(self, project_root):
        """Verify no dev_user special privileges in deps.py"""
        deps_file = project_root / "app" / "api" / "core" / "deps.py"
        content = read_file_utf8(deps_file)

        # Should not have dev_user privilege checks
        assert 'user_id == "dev_user"' not in content
        assert "user_id == 'dev_user'" not in content

    def test_no_development_mode_bypass(self, project_root):
        """Verify no development mode auth bypass in dependencies.py"""
        deps_file = project_root / "app" / "api" / "core" / "dependencies.py"
        content = read_file_utf8(deps_file)

        # Should not contain development mode bypass returning mock user
        assert '"dev-user"' not in content


class TestSecurityHeaders:
    """Verify security headers middleware is properly configured"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent

    def test_security_middleware_exists(self, project_root):
        """Verify security middleware file exists"""
        middleware_file = project_root / "app" / "api" / "core" / "security_middleware.py"
        assert middleware_file.exists(), "Security middleware file not found"

    def test_csp_header_configured(self, project_root):
        """Verify CSP header is configured in middleware"""
        middleware_file = project_root / "app" / "api" / "core" / "security_middleware.py"
        content = read_file_utf8(middleware_file)

        assert 'Content-Security-Policy' in content
        assert "default-src 'self'" in content

    def test_xframe_options_configured(self, project_root):
        """Verify X-Frame-Options header is configured"""
        middleware_file = project_root / "app" / "api" / "core" / "security_middleware.py"
        content = read_file_utf8(middleware_file)

        assert 'X-Frame-Options' in content
        assert 'DENY' in content

    def test_security_middleware_added_to_app(self, project_root):
        """Verify security middleware is added to FastAPI app"""
        main_file = project_root / "app" / "api" / "main.py"
        content = read_file_utf8(main_file)

        assert 'SecurityHeadersMiddleware' in content

    def test_hsts_configured(self, project_root):
        """Verify HSTS header is configured"""
        middleware_file = project_root / "app" / "api" / "core" / "security_middleware.py"
        content = read_file_utf8(middleware_file)

        assert 'Strict-Transport-Security' in content


class TestHttpOnlyCookies:
    """Verify HttpOnly cookie authentication is properly configured"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent

    def test_cookie_auth_module_exists(self, project_root):
        """Verify cookie auth module exists"""
        cookie_file = project_root / "app" / "api" / "core" / "cookie_auth.py"
        assert cookie_file.exists(), "Cookie auth module not found"

    def test_httponly_flag_set(self, project_root):
        """Verify HttpOnly flag is set for cookies"""
        cookie_file = project_root / "app" / "api" / "core" / "cookie_auth.py"
        content = read_file_utf8(cookie_file)

        assert 'HTTPONLY = True' in content or 'httponly=True' in content

    def test_samesite_strict(self, project_root):
        """Verify SameSite=Strict is set"""
        cookie_file = project_root / "app" / "api" / "core" / "cookie_auth.py"
        content = read_file_utf8(cookie_file)

        assert 'samesite' in content.lower()
        assert 'strict' in content.lower()

    def test_frontend_uses_credentials(self, project_root):
        """Verify frontend uses withCredentials for cookie auth"""
        api_file = project_root / "frontend" / "src" / "services" / "api.ts"
        content = read_file_utf8(api_file)

        assert 'withCredentials: true' in content

    def test_frontend_no_localstorage_tokens(self, project_root):
        """Verify frontend doesn't store tokens in localStorage"""
        auth_store = project_root / "frontend" / "src" / "store" / "authStore.ts"
        content = read_file_utf8(auth_store)

        # Should not have localStorage.setItem for tokens
        assert 'localStorage.setItem' not in content

    def test_auth_router_sets_cookies(self, project_root):
        """Verify auth router sets HttpOnly cookies on login"""
        auth_file = project_root / "app" / "api" / "routers" / "auth.py"
        content = read_file_utf8(auth_file)

        assert 'set_auth_cookies' in content
        assert 'clear_auth_cookies' in content


class TestCORSConfiguration:
    """Verify CORS is properly configured"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent

    def test_no_wildcard_cors(self, project_root):
        """Verify CORS doesn't use wildcards"""
        main_file = project_root / "app" / "api" / "main.py"
        content = read_file_utf8(main_file)

        # Should use cors_config from security_middleware, not wildcards
        assert 'get_cors_config' in content
        # Should not have direct wildcard assignment
        lines = [l for l in content.split('\n') if 'allow_methods' in l or 'allow_headers' in l]
        for line in lines:
            assert '["*"]' not in line, f"Found wildcard in: {line}"

    def test_cors_uses_config(self, project_root):
        """Verify CORS uses the security config"""
        main_file = project_root / "app" / "api" / "main.py"
        content = read_file_utf8(main_file)

        assert 'cors_config["allow_origins"]' in content or 'cors_config[' in content


class TestSecretsManager:
    """Verify secrets manager is properly configured"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent

    def test_secrets_manager_exists(self, project_root):
        """Verify secrets manager module exists"""
        secrets_file = project_root / "app" / "api" / "core" / "secrets_manager.py"
        assert secrets_file.exists(), "Secrets manager not found"

    def test_required_secrets_defined(self, project_root):
        """Verify required secrets are defined"""
        secrets_file = project_root / "app" / "api" / "core" / "secrets_manager.py"
        content = read_file_utf8(secrets_file)

        required_secrets = [
            "JWT_SECRET_KEY",
            "ENCRYPTION_MASTER_KEY",
            "ENCRYPTION_SALT",
            "NEO4J_PASSWORD",
        ]

        for secret in required_secrets:
            assert secret in content, f"Required secret {secret} not defined"

    def test_startup_validation_configured(self, project_root):
        """Verify secrets validation at startup is configured"""
        main_file = project_root / "app" / "api" / "main.py"
        content = read_file_utf8(main_file)

        assert 'validate_secrets_on_startup' in content

    def test_validation_function_exists(self, project_root):
        """Verify validation function is defined"""
        secrets_file = project_root / "app" / "api" / "core" / "secrets_manager.py"
        content = read_file_utf8(secrets_file)

        assert 'def validate_secrets_on_startup' in content


class TestEnvExample:
    """Verify .env.example is properly configured"""

    @pytest.fixture
    def project_root(self):
        return Path(__file__).parent.parent.parent

    def test_env_example_exists(self, project_root):
        """Verify .env.example file exists"""
        env_file = project_root / ".env.example"
        assert env_file.exists(), ".env.example not found"

    def test_no_hardcoded_passwords_in_env_example(self, project_root):
        """Verify .env.example has no hardcoded password values"""
        env_file = project_root / ".env.example"
        content = read_file_utf8(env_file)

        # Should not contain known insecure passwords
        assert 'graphrag2024' not in content
        assert 'your-secret-key' not in content
        assert 'dev-secret-key' not in content

    def test_security_instructions_present(self, project_root):
        """Verify security instructions are in .env.example"""
        env_file = project_root / ".env.example"
        content = read_file_utf8(env_file)

        # Should have security warnings
        assert 'SECURITY' in content.upper() or 'REQUIRED' in content.upper()
        # Should mention how to generate secrets
        assert 'openssl rand' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
