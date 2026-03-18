from __future__ import annotations

import time

import httpx

from slack_mcp.auth import WorkspaceCredential


class SlackAPIError(Exception):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class SlackClient:
    BASE_URL = "https://slack.com/api/"

    def __init__(self, credential: WorkspaceCredential) -> None:
        self._headers = {
            "Authorization": f"Bearer {credential.token}",
            "Cookie": f"d={credential.d_cookie}",
        }

    def get(self, method: str, **params: object) -> dict:
        return self._request(method, params)

    def _request(self, method: str, params: dict, *, _retry: bool = True) -> dict:
        with httpx.Client() as http:
            response = http.post(
                f"{self.BASE_URL}{method}",
                data=params,
                headers=self._headers,
            )

        if response.status_code == 429:
            if _retry:
                retry_after = int(response.headers.get("Retry-After", "1"))
                time.sleep(retry_after)
                return self._request(method, params, _retry=False)
            response.raise_for_status()

        if response.status_code >= 500:
            response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            raise SlackAPIError(data.get("error", "unknown_error"))

        return data

    def get_paginated(
        self, method: str, key: str, limit: int, **params: object
    ) -> list[dict]:
        results: list[dict] = []
        cursor: str | None = None

        while len(results) < limit:
            batch_limit = min(limit - len(results), 200)
            request_params: dict = {**params, "limit": batch_limit}
            if cursor:
                request_params["cursor"] = cursor

            data = self._request(method, request_params)
            results.extend(data.get(key, []))

            cursor = data.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break

        return results[:limit]
