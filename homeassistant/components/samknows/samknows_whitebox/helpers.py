import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)


async def _make_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    json: dict | None = None,
    *,
    headers: dict | None = None,
    token: str | None = None,
) -> dict:
    """
    Makes a request, optionally authenticated,
    and returns the data if return code is OK.
    """

    if headers is None:
        headers = {}
    if token is not None and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"

    async with session.request(
        method,
        url,
        headers=headers,
        json=json,
    ) as raw_response:
        response = await raw_response.json()
        if response.get("code") == "OK":
            return response.get("data")
        _LOGGER.error(
            "Request failed: %s %s\n%s\n%s\n%s", method, url, json, headers, response
        )
        raise RequestFailed()
