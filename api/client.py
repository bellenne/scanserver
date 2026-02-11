from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("api")


class ApiClient:
    def __init__(self, base_url: str, timeout_s: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    def get_users(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/v1/users/"
        r = self._client.get(url)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected users response format")
        return data

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        url = f"{self.base_url}{path}"
        log.info("POST %s %s", url, payload)
        r = self._client.post(url, json=payload)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Печатаем тело (Laravel validation errors)
            body = ""
            try:
                body = e.response.text
            except Exception:
                body = "<no body>"
            log.warning("HTTP %s for %s. Response: %s", e.response.status_code, url, body)
            raise

        
        if not r.content:
            return None
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}
    
    def get_user(self, user_id: int) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/users/{int(user_id)}"
        r = self._client.get(url)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected user response format")
        return data
