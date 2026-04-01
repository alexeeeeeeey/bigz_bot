import asyncio
from collections.abc import Mapping
from typing import Any

import aiohttp
from yarl import URL


class BaseApi:
    def __init__(
        self,
        base_url: str | URL,
        *,
        timeout: float = 15.0,
        retries: int = 3,
        retry_delay: float = 0.5,
        retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.base_url = URL(str(base_url))
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.retries = retries
        self.retry_delay = retry_delay
        self.retry_statuses = retry_statuses
        self.headers = dict(headers or {})
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers=self.headers,
            )
        return self._session

    def _build_url(self, path: str | URL) -> URL:
        if isinstance(path, URL):
            url = path
        else:
            url = URL(path)

        if url.is_absolute():
            return url

        return self.base_url.join(URL(str(path).lstrip("/")))

    def _get_retry_delay(
        self,
        attempt: int,
        response: aiohttp.ClientResponse | None = None,
    ) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass

        return self.retry_delay * (2**attempt)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def request(
        self,
        method: str,
        path: str | URL,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
    ) -> aiohttp.ClientResponse:
        session = await self._ensure_session()
        url = self._build_url(path)
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                response = await session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    data=data,
                    headers=headers,
                    timeout=timeout,
                )

                if response.status in self.retry_statuses:
                    if attempt >= self.retries:
                        response.raise_for_status()

                    response.release()
                    await asyncio.sleep(self._get_retry_delay(attempt, response))
                    continue

                response.raise_for_status()
                return response
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise
                await asyncio.sleep(self._get_retry_delay(attempt))

        raise RuntimeError("Request failed after retries") from last_error

    async def get(
        self,
        path: str | URL,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
    ) -> aiohttp.ClientResponse:
        return await self.request(
            "GET",
            path,
            params=params,
            headers=headers,
            timeout=timeout,
        )

    async def post(
        self,
        path: str | URL,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
    ) -> aiohttp.ClientResponse:
        return await self.request(
            "POST",
            path,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout,
        )

    async def put(
        self,
        path: str | URL,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
    ) -> aiohttp.ClientResponse:
        return await self.request(
            "PUT",
            path,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout,
        )

    async def patch(
        self,
        path: str | URL,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
    ) -> aiohttp.ClientResponse:
        return await self.request(
            "PATCH",
            path,
            params=params,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout,
        )

    async def delete(
        self,
        path: str | URL,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | aiohttp.ClientTimeout | None = None,
    ) -> aiohttp.ClientResponse:
        return await self.request(
            "DELETE",
            path,
            params=params,
            headers=headers,
            timeout=timeout,
        )
