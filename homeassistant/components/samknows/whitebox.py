from datetime import datetime
import logging

import aiohttp
import jwt

_LOGGER = logging.getLogger(__name__)


class UnitDetails:
    """Contains information about a specific unit."""

    def __init__(
        self,
        unit_id: int,
        front_name: str | None = None,
        mac_address: str | None = None,
        base: str | None = None,
        serial_number: str | None = None,
        sw_version: str | None = None,
        is_tt_compatible: bool = False,
    ):
        self.unit_id = unit_id
        self.front_name = front_name
        self.mac_address = mac_address
        self.base = base
        self.serial_number = serial_number
        self.sw_version = sw_version
        self.is_tt_compatible = is_tt_compatible

        self.metrics = {}


class WhiteboxApi:
    """Connects to the SamKnows.one API and fetches Whitebox data."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.access_token = None
        self.access_token_expiry = None
        self.refresh_token = None
        self.refresh_token_expiry = None
        self.units: list[UnitDetails] = []
        self._unit_cache = {}

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

    async def _get_fresh_token(self) -> str:
        if datetime.now() >= self.access_token_expiry:
            refreshed = await self._refresh_token()
            if not refreshed:
                logged_in = await self.login(self._session)
                if not logged_in:
                    raise CouldNotAuthenticate()
        return self.access_token

    async def _refresh_token(self) -> bool:
        if datetime.now() >= self.refresh_token_expiry:
            return False

        async with self._session.post(
            "https://sentinel-api.cloud.samknows.com/renew",
            headers={"Content-Type": "application/json"},
            json={"refreshToken": self.refresh_token},
        ) as resp:
            try:
                response = await resp.json()
                _LOGGER.info(response)
                if response.get("code") == "OK":
                    new_access_token = response["data"]["accessToken"]
                    self.access_token = new_access_token
                    self.access_token_expiry = self._get_token_expiry(
                        self, new_access_token
                    )
                    return True
                return False
            except Exception as e:
                _LOGGER.error("Failed to renew access token, %s", e)
                return False

    # TODO dangerous arguments
    async def _make_request(
        self, method: str, url: str, json: dict = None, headers: dict | None = {}
    ):
        token = await self._get_fresh_token()
        async with self._session.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"} | headers,
            json=json,
        ) as resp:
            response = await resp.json()
            if response.get("code") == "OK":
                return response.get("data")
            else:
                _LOGGER.error("Request failed: %s %s\n%s", method, url, json)
                raise RequestFailed()

    async def fetch_data(self):
        """Main function to fetch unit(s) information."""
        await self._fetch_units()

        # _LOGGER.info("Units fetched, %s [Cache %s]", self.units, self._unit_cache)

        today = datetime.now().strftime("%Y-%m-%d")
        metric = "httpgetmt"

        units = {}

        for unit in self.units:
            data = await self._make_request(
                "GET",
                f"https://unit-analytics-api.cloud.samknows.com/{unit.unit_id}/scheduled_tests_daily?date={today}&metric={metric}",
            )
            if len(data["results"]) > 0:
                unit.metrics[metric] = data["results"][0][
                    "metricValue"
                ]  # TODO log all results not just the first
                _LOGGER.info("Metrics, %s", unit.metrics)
                units[unit.unit_id] = unit

        return units

        # token = await self._get_fresh_token()
        # async with self._session.get(
        #     "",
        #     headers={"Authorization": f"Bearer {token}"},
        # ) as resp:
        #     response = await resp.json()
        #     if response.get("code") == "OK":
        #         return {"102479809": response["data"]}
        #     else:
        #         raise RequestFailed()

    async def _fetch_units(self):
        response = await self._make_request(
            "GET",
            "https://sentinel-api.cloud.samknows.com/myAccessibles",
        )
        self.units = []
        for unit_data in response["units"]:
            unit_id = unit_data["unitId"]
            if self._unit_cache.get(unit_id) is not None:
                _LOGGER.info(f"Adding unit {unit_id} from cache")
                self.units.append(self._unit_cache.get(unit_id))
            else:
                _LOGGER.info(f"Unit {unit_id}: cache miss, fetching")
                unit = await self._fetch_unit_information(unit_id)
                self.units.append(unit)
                self._unit_cache[unit_id] = unit

    async def _fetch_unit_information(self, unit_id: int) -> UnitDetails:
        data = await self._make_request(
            "GET", f"https://zeus-api.samknows.one/units/{unit_id}"
        )
        return UnitDetails(
            unit_id=data["id"],
            front_name=data["front_name"],
            mac_address=data["mac"],
            base=data["base"],
            serial_number=data["serial_number"],
            sw_version=data["package_version"],
            is_tt_compatible=data["is_tt_compatible"],
        )


class RefreshFailed(Exception):
    """Raised when refreshing an auth token has failed."""


class CouldNotAuthenticate(Exception):
    """Raised when authentication has failed."""


class RequestFailed(Exception):
    """Raised when a request returns a non-OK error code."""
