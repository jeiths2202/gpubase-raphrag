"""
Connector Manager
Factory and manager for external resource connectors.
"""
from typing import Optional, Dict, Type
from functools import lru_cache

from .base import BaseConnector
from ..models.external_connection import ExternalResourceType


class ConnectorManager:
    """
    Factory for creating and managing external resource connectors.
    """

    _connectors: Dict[ExternalResourceType, Type[BaseConnector]] = {}

    def __init__(self):
        self._register_connectors()

    def _register_connectors(self):
        """Register all available connectors"""
        from .notion_connector import NotionConnector
        from .github_connector import GitHubConnector
        from .google_drive_connector import GoogleDriveConnector
        from .onenote_connector import OneNoteConnector
        from .confluence_connector import ConfluenceConnector

        self._connectors = {
            ExternalResourceType.NOTION: NotionConnector,
            ExternalResourceType.GITHUB: GitHubConnector,
            ExternalResourceType.GOOGLE_DRIVE: GoogleDriveConnector,
            ExternalResourceType.ONENOTE: OneNoteConnector,
            ExternalResourceType.CONFLUENCE: ConfluenceConnector
        }

    def get_connector(
        self,
        resource_type: ExternalResourceType,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        api_token: Optional[str] = None,
        config: Optional[Dict] = None
    ) -> BaseConnector:
        """
        Create a connector instance for the specified resource type.

        Args:
            resource_type: Type of external resource
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            api_token: API token (for non-OAuth resources)
            config: Additional configuration

        Returns:
            Configured connector instance
        """
        connector_class = self._connectors.get(resource_type)
        if not connector_class:
            raise ValueError(f"Unknown resource type: {resource_type}")

        return connector_class(
            access_token=access_token,
            refresh_token=refresh_token,
            api_token=api_token,
            config=config
        )

    def get_available_resources(self) -> Dict[str, Dict]:
        """Get list of all available resource types with info"""
        from ..models.external_connection import EXTERNAL_RESOURCE_CONFIGS

        return {
            rt.value: {
                "display_name": cfg.display_name,
                "icon": cfg.icon,
                "auth_type": cfg.auth_type.value,
                "description": cfg.description,
                "supported_formats": cfg.supported_formats
            }
            for rt, cfg in EXTERNAL_RESOURCE_CONFIGS.items()
        }

    def is_supported(self, resource_type: str) -> bool:
        """Check if a resource type is supported"""
        try:
            return ExternalResourceType(resource_type) in self._connectors
        except ValueError:
            return False


@lru_cache()
def get_connector_manager() -> ConnectorManager:
    """Get singleton connector manager instance"""
    return ConnectorManager()
