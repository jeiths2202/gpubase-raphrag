"""IMS Semantic Search API Client"""
import json
import sys
from typing import Iterator, Optional

import requests

from .config import API_BASE_URL, API_PREFIX, AUTH_USERNAME, AUTH_PASSWORD


class IMSClient:
    """API client for IMS semantic search endpoints."""

    def __init__(self, base_url: str = API_BASE_URL, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}{API_PREFIX}"
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def login(self, username: str = AUTH_USERNAME, password: str = AUTH_PASSWORD) -> str:
        """Authenticate and get access token."""
        resp = self.session.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        token = resp.json()["data"]["access_token"]
        self.session.headers["Authorization"] = f"Bearer {token}"
        return token

    def search(self, query: str, limit: int = 10, product: Optional[str] = None) -> dict:
        """POST /ims-chat/search"""
        payload = {"query": query, "limit": limit}
        if product:
            payload["product_filter"] = product
        resp = self.session.post(f"{self.api_url}/search", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_issue(self, ims_id: str) -> dict:
        """GET /ims-chat/issues/{ims_id}"""
        resp = self.session.get(f"{self.api_url}/issues/{ims_id}")
        resp.raise_for_status()
        return resp.json()

    def get_related(self, ims_id: str) -> dict:
        """GET /ims-chat/issues/{ims_id}/related"""
        resp = self.session.get(f"{self.api_url}/issues/{ims_id}/related")
        resp.raise_for_status()
        return resp.json()

    def summarize(self, ims_id: str, language: str = "auto") -> dict:
        """POST /ims-chat/issues/summarize"""
        resp = self.session.post(
            f"{self.api_url}/issues/summarize",
            json={"ims_id": ims_id, "language": language},
        )
        resp.raise_for_status()
        return resp.json()

    def chat_stream(
        self, query: str, limit: int = 5, include_related: bool = True, language: str = "auto"
    ) -> Iterator[dict]:
        """POST /ims-chat/chat/semantic → SSE stream iterator"""
        resp = self.session.post(
            f"{self.api_url}/chat/semantic",
            json={
                "query": query,
                "search_limit": limit,
                "include_related": include_related,
                "language": language,
            },
            stream=True,
        )
        resp.raise_for_status()

        event_type = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    yield {"event": event_type, "data": data}
                except json.JSONDecodeError:
                    continue

    def create_knowledge(self, ims_ids: list, title: str, language: str = "auto") -> dict:
        """POST /ims-chat/knowledge/create"""
        resp = self.session.post(
            f"{self.api_url}/knowledge/create",
            json={"ims_ids": ims_ids, "title": title, "language": language},
        )
        resp.raise_for_status()
        return resp.json()
