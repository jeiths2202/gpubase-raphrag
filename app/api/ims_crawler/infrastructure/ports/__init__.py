"""
Ports - Interfaces for external dependencies

Defines abstract interfaces that infrastructure adapters must implement.
Enables dependency inversion: domain depends on abstractions, not concretions.
"""

from .crawler_port import CrawlerPort
from .nl_parser_port import NLParserPort
from .credentials_repository_port import CredentialsRepositoryPort
from .issue_repository_port import IssueRepositoryPort
from .embedding_service_port import EmbeddingServicePort

__all__ = [
    "CrawlerPort",
    "NLParserPort",
    "CredentialsRepositoryPort",
    "IssueRepositoryPort",
    "EmbeddingServicePort",
]
