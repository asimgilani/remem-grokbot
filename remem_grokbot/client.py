from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

# Forbidden: POST /v1/ingest. Live path is POST /v1/documents/ingest.
INGEST_PATH = "/v1/documents/ingest"
QUERY_PATH = "/v1/query"
DEFAULT_API_URL = "https://api.remem.io"


class RememConfigError(RuntimeError):
    """Missing or invalid Remem client configuration."""


class RememClient:
    """HTTP client for live Remem. Dual auth. JSON ingest first."""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_url = (api_url or os.getenv("REMEM_API_URL") or DEFAULT_API_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("REMEM_API_KEY", "")
        self.timeout = timeout

    def headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        if not self.api_key:
            raise RememConfigError("REMEM_API_KEY is not set")
        out = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if idempotency_key:
            out["Idempotency-Key"] = idempotency_key
        return out

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = self.headers(idempotency_key=idempotency_key)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.request(
                method,
                f"{self.api_url}{path}",
                headers=headers,
                json=json_body,
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def query(self, payload: dict[str, Any]) -> Any:
        return await self.request("POST", QUERY_PATH, json_body=payload)

    async def ingest(self, payload: dict[str, Any]) -> Any:
        return await self.request(
            "POST",
            INGEST_PATH,
            json_body=payload,
            idempotency_key=str(uuid.uuid4()),
        )
