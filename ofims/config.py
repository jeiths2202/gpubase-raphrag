"""CLI configuration"""
import os

API_BASE_URL = os.getenv("OFIMS_API_URL", "http://localhost:9000")
API_PREFIX = "/api/v1/ims-chat"
AUTH_USERNAME = os.getenv("OFIMS_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("OFIMS_PASSWORD", "SecureAdm1nP@ss2024!")
