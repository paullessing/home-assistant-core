import logging
import aiohttp
from datetime import date, datetime, time
import jwt
from dataclasses import dataclass

from .api_config import SENTINEL_API_URL
from .errors import CouldNotAuthenticate

_LOGGER = logging.getLogger(__name__)


@dataclass
class ExpirableToken:
    """
    Wraps information about a token + its expiry.
    """

    token: str
    expiry: datetime

    def is_expired(self) -> bool:
        return datetime.now() >= self.expiry


class AuthManager:
    """
    Manages authentication tokens for the Whitebox API.
    """

    username: str
    password: str
    access_token: ExpirableToken | None = None
    refresh_token: ExpirableToken | None = None
    _session: aiohttp.ClientSession

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ):
        self.username = username
        self.password = password
        self._session = session

    def __getstate__(self):
        state = self.__dict__.copy()
        del state["_session"]
        return state

    async def login(self):
        """
        Logs in, storing session details locally.
        Returns True on success, False otherwise.
        """

        async with self._session.post(
            f"https://{SENTINEL_API_URL}/login",
            json={
                "email": self.username,
                "password": self.password,
                "device": "1234567890",
            },
            headers={"Content-Type": "application/json"},
        ) as raw_response:
            try:
                response = await raw_response.json()
                # _LOGGER.info(response)
            except aiohttp.ClientConnectorError:
                return False

            if response.get("code") != "OK":
                return False

            access_token_value = response["data"]["accessToken"]
            self.access_token = ExpirableToken(
                token=access_token_value,
                expiry=_get_token_expiry(token=access_token_value),
            )

            refresh_token = response["data"]["refreshToken"]
            self.refresh_token = ExpirableToken(
                token=refresh_token["token"],
                expiry=datetime.strptime(
                    refresh_token["expiresAt"], "%Y-%m-%d %H:%M:%S"
                ),
            )

            _LOGGER.info(
                "Successfully logged in. Expiry is %s | %s",
                self.access_token.expiry,
                self.refresh_token.expiry,
            )
            return True

    async def get_fresh_token(self) -> str:
        """
        Ensures that the token is fresh, then returns it.
        """

        if self.access_token is not None and not self.access_token.is_expired():
            return self.access_token.token

        refreshed = await self._refresh_access_token()
        if not refreshed:
            await self.login()
        if self.access_token is None:
            raise CouldNotAuthenticate()

        return self.access_token.token

    async def _refresh_access_token(self) -> bool:
        """
        Refresh the current auth token.
        Returns True if the token was renewed.
        Returns False if an error occurred during renewal.
        TODO raise the correct errors.
        """
        if self.refresh_token is None or self.refresh_token.is_expired():
            return False

        async with self._session.post(
            f"https://{SENTINEL_API_URL}/renew",
            headers={"Content-Type": "application/json"},
            json={"refreshToken": self.refresh_token.token},
        ) as raw_response:
            try:
                response = await raw_response.json()
                # _LOGGER.info(response)
                if response.get("code") == "OK":
                    new_access_token = response["data"]["accessToken"]
                    self.access_token = new_access_token
                    self.access_token_expiry = _get_token_expiry(new_access_token)
                    return True
                return False
            except Exception:
                _LOGGER.warning("Failed to renew access token", exc_info=True)
                return False


def _get_token_expiry(token: str) -> datetime:
    """
    Calculates the expiry date of a JWT string.
    """

    decoded_data = jwt.decode(
        jwt=token,
        algorithms=["HS256", "RS256"],
        options={"verify_signature": False},
    )
    # _LOGGER.warning("Decoded JWT, %s", decoded_data)
    return datetime.fromtimestamp(decoded_data["exp"])
