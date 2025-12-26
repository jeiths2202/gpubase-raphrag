"""
External Resource Connectors
Provides connectors for integrating external knowledge sources.
"""
from .base import BaseConnector, ConnectorDocument, ConnectorResult
from .manager import ConnectorManager, get_connector_manager

__all__ = [
    "BaseConnector",
    "ConnectorDocument",
    "ConnectorResult",
    "ConnectorManager",
    "get_connector_manager"
]
