from datetime import datetime
import logging

import aiohttp
import jwt

_LOGGER = logging.getLogger(__name__)


class WhiteboxApi:
    """Connects to the SamKnows.one API and fetches Whitebox data."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.access_token = None
        self.access_token_expiry = None
        self.refresh_token = None
        self.refresh_token_expiry = None

    async def login(self, session: aiohttp.ClientSession = None):
        if session is None:
            self._session = aiohttp.ClientSession()
            session = self._session
        async with session.post(
            "https://sentinel-api.cloud.samknows.com/login",
            json={
                "email": self.username,
                "password": self.password,
                "device": "1234567890",
            },
            headers={"Content-Type": "application/json"},
        ) as resp:
            try:
                response = await resp.json()
                _LOGGER.info(response)
                if response.get("code") == "OK":
                    self.access_token = response["data"]["accessToken"]
                    self.access_token_expiry = self._get_token_expiry(
                        token=self.access_token
                    )
                    refresh_token = response["data"]["refreshToken"]
                    self.refresh_token = refresh_token["token"]
                    self.refresh_token_expiry = datetime.strptime(
                        refresh_token["expiresAt"], "%Y-%m-%d %H:%M:%S"
                    )
                    _LOGGER.info(
                        "Successfully logged in. Expiry is %s | %s",
                        self.access_token_expiry,
                        self.refresh_token_expiry,
                    )
                    return True
                return False
            except aiohttp.ClientConnectorError:
                return False

    def _get_token_expiry(self, token: str):
        decoded_data = jwt.decode(
            jwt=token,
            algorithms=["HS256", "RS256"],
            options={"verify_signature": False},
        )
        _LOGGER.warning("Decoded JWT, %s", decoded_data)
        return datetime.fromtimestamp(decoded_data["exp"])
