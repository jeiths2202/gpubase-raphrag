"""
IMS Crawler Module - Clean Architecture Implementation

This module provides IMS (Issue Management System) crawling capabilities
integrated into the HybridRAG KMS platform.

Architecture Layers:
- domain: Business entities and domain logic (framework-independent)
- application: Use cases and application services
- infrastructure: External adapters (crawlers, storage, LLM)
- presentation: FastAPI routers and API models
"""

__version__ = "1.0.0"
