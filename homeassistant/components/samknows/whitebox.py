from datetime import datetime
import logging

import aiohttp
import jwt

from .api_config import *
from .models import *

_LOGGER = logging.getLogger(__name__)


class WhiteboxApi:
    """Connects to the SamKnows.one API and fetches Whitebox data."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self.access_token = None
        self.access_token_expiry = None
        self.refresh_token = None
        self.refresh_token_expiry = None
        self.units: list[UnitDetails] = []
        self._unit_cache = {}
        self._session = None

    async def login(self, session: aiohttp.ClientSession = None):
        if session is None:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            session = self._session
        async with session.post(
            f"https://{SENTINEL_API_URL}/login",
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
                    self.access_token_expiry = _get_token_expiry(
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

    async def _get_fresh_token(self) -> str:
        """Ensures that the token is fresh, then returns it."""

        if datetime.now() < self.access_token_expiry:
            return self.access_token

        refreshed = await self._refresh_access_token()
        if not refreshed:
            logged_in = await self.login()
            if not logged_in:
                raise CouldNotAuthenticate()

    async def _refresh_access_token(self) -> bool:
        """Refresh the current auth token.
        Returns True if the token was renewed.
        Returns False if an error occurred during renewal.
        TODO raise the correct errors.
        """
        if datetime.now() >= self.refresh_token_expiry:
            return False

        async with self._session.post(
            f"https://{SENTINEL_API_URL}/renew",
            headers={"Content-Type": "application/json"},
            json={"refreshToken": self.refresh_token},
        ) as resp:
            try:
                response = await resp.json()
                _LOGGER.info(response)
                if response.get("code") == "OK":
                    new_access_token = response["data"]["accessToken"]
                    self.access_token = new_access_token
                    self.access_token_expiry = _get_token_expiry(new_access_token)
                    return True
                return False
            except Exception as e:
                _LOGGER.error("Failed to renew access token, %s", e)
                return False

    async def fetch_data(self) -> dict[int, UnitUpdate]:
        """Main function to fetch unit(s) information."""
        self.units = await self._fetch_units()

        # _LOGGER.info("Units fetched, %s [Cache %s]", self.units, self._unit_cache)

        # date = datetime.now().strftime("%d-%m-%Y")
        # yday = (datetime.now() - timedelta(days=7)).strftime("%d-%m-%Y")

        # x = (
        #     await _make_request(
        #         self._session,
        #         "POST",
        #         f"https://{UNIT_ANALYTICS_API_URL}/{unit.unit_id}/metric_results",
        #         json={
        #             "date": {"from": yday, "to": date},
        #             "includeAggregated": True,
        #             "includeTotal": True,
        #             "localTargetSetResultsOnly": True,
        #             "aggregation": "daily",
        #             "metric": metric,
        #         },
        #         token=await self._get_fresh_token(),
        #     )
        #     for unit in self.units
        #     for metric in ("httpgetmt", "httppostmt", "udpLatency", "udpPacketLoss")
        # )

        # async for data in x:
        #     _LOGGER.info("Fetched units data %s", data)

        # TODO make requests in parallel

        return {
            unit.unit_id: UnitUpdate(
                details=unit,
                data=await self.fetch_unit_measurements(
                    unit.unit_id, metrics=("httpgetmt", "httppostmt")
                ),
            )
            for unit in self.units
        }

    async def _fetch_units(self) -> list[UnitDetails]:
        """Loads all units the user has access to and returns them."""

        response = await _make_request(
            self._session,
            "GET",
            f"https://{SENTINEL_API_URL}/myAccessibles",
            token=await self._get_fresh_token(),
        )
        units = []
        for unit_data in response["units"]:
            unit_id = unit_data["unitId"]
            if unit_id in self._unit_cache:
                _LOGGER.info(f"Adding unit {unit_id} from cache")
                units.append(self._unit_cache[unit_id])
            else:
                _LOGGER.info(f"Unit {unit_id}: cache miss, fetching")
                unit = await self._fetch_unit_information(unit_id)
                self._unit_cache[unit_id] = unit
                units.append(unit)
        return units

    async def _fetch_unit_information(self, unit_id: int) -> UnitDetails:
        """Fetch all metadata for a given unit."""

        data = await _make_request(
            self._session,
            "GET",
            f"https://{ZEUS_API_URL}/units/{unit_id}",
            token=await self._get_fresh_token(),
        )
        _LOGGER.warn(data)
        return UnitDetails(unit_id=data["id"], **data)

    async def fetch_unit_measurements(
        self, unit_id: int, metrics: list[str] = None, date: str | None = None
    ) -> dict[int, int | str | float]:
        """Fetches the most recent measurements for a given unit."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        metric_results = {}

        for metric in metrics:
            data = await _make_request(
                self._session,
                "GET",
                f"https://{UNIT_ANALYTICS_API_URL}/{unit_id}/scheduled_tests_daily?date={date}&metric={metric}",
                token=await self._get_fresh_token(),
            )
            if len(data["results"]) > 0:
                metric_results[metric] = data["results"][0][
                    "metricValue"
                ]  # TODO log all results not just the first

        return metric_results


async def _make_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    json: dict = None,
    *,
    headers: dict | None = None,
    token: str | None = None,
) -> dict:
    """Makes a request, optionally authenticated, and returns the data if return code is OK."""

    if headers is None:
        headers = {}
    if token is not None and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"

    async with session.request(
        method,
        url,
        headers=headers,
        json=json,
    ) as resp:
        response = await resp.json()
        if response.get("code") == "OK":
            return response.get("data")
        _LOGGER.error(
            "Request failed: %s %s\n%s\n%s\n%s", method, url, json, headers, response
        )
        raise RequestFailed()


def _get_token_expiry(token: str) -> datetime:
    """Calculates the expiry date of a JWT string."""

    decoded_data = jwt.decode(
        jwt=token,
        algorithms=["HS256", "RS256"],
        options={"verify_signature": False},
    )
    # _LOGGER.warning("Decoded JWT, %s", decoded_data)
    return datetime.fromtimestamp(decoded_data["exp"])


class RefreshFailed(Exception):
    """Raised when refreshing an auth token has failed."""


class CouldNotAuthenticate(Exception):
    """Raised when authentication has failed."""


class RequestFailed(Exception):
    """Raised when a request returns a non-OK error code."""
