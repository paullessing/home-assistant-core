"""
Main API class.
"""

import asyncio
import logging
from pprint import pprint
import urllib.parse
from datetime import datetime

import aiohttp

from .helpers import _make_request
from .auth import AuthManager
from .api_config import SENTINEL_API_URL, UNIT_ANALYTICS_API_URL, ZEUS_API_URL
from .models import (
    Measurements,
    ScheduledTestResult,
    ScheduledTests,
    ScheduledUnitTests,
    UnitDetails,
    UnitUpdate,
)

_LOGGER = logging.getLogger(__name__)

UNIT_ANALYTICS_API = urllib.parse.urlparse(f"https://{UNIT_ANALYTICS_API_URL}")


class WhiteboxApi:
    """
    Connects to the SamKnows.one API and fetches Whitebox data.
    """

    units: list[UnitDetails]
    _auth: AuthManager
    _unit_cache: dict[int, UnitDetails]
    _session: aiohttp.ClientSession

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._auth = AuthManager(username, password, session)
        self.units = []
        self._unit_cache = {}
        self._session = session

    def __getstate__(self):
        """
        Get state for pickling. Not used for production, just for debugging.
        """

        state = self.__dict__.copy()
        # Delete unpickleable property. This needs to be set manually when restoring.
        del state["_session"]
        return state

    async def login(self) -> bool:
        """
        Logs in, storing session details locally.
        Returns True on success, False otherwise.
        """

        return await self._auth.login()

    async def fetch_all_unit_updates(self) -> dict[int, UnitUpdate]:
        """
        Main function to fetch unit(s) information.
        """

        self.units = await self.fetch_user_units()

        _LOGGER.debug("Units: %s", [unit["unit_id"] for unit in self.units])

        measurements = {
            unit_id: measurement
            for (unit_id, measurement) in await asyncio.gather(
                *(self._fetch_unit_measurements(unit["unit_id"]) for unit in self.units)
            )
        }

        # _LOGGER.debug(
        #     {
        #         unit_id: {
        #             "httpgetmt": len(measurement["httpgetmt"]),
        #             "httppostmt": len(measurement["httppostmt"]),
        #         }
        #         for (unit_id, measurement) in measurements.items()
        #     }
        # )

        return {
            unit["unit_id"]: UnitUpdate(
                {
                    "unit": unit,
                    "measurements": measurements[unit["unit_id"]],
                }
            )
            for unit in self.units
        }

    async def fetch_user_units(self, force_fresh=False) -> list[UnitDetails]:
        """
        Loads all units the user has access to and returns them.
        """

        response = await _make_request(
            self._session,
            "GET",
            f"https://{SENTINEL_API_URL}/myAccessibles",
            token=await self._auth.get_fresh_token(),
        )
        units: list[UnitDetails] = await asyncio.gather(
            *(
                self._get_unit(unit_data["unitId"], force_fresh)
                for unit_data in response["units"]
            )
        )

        return units

    # async def fetch_scheduled_unit_tests(self, unit_id: int) -> ScheduledUnitTests:
    #     date =

    # async def fetch_scheduled_unit_test(self, unit_id: int, metric: str, date: str) -> ScheduledTests:

    async def _get_unit(self, unit_id: int, force_fresh=False) -> UnitDetails:
        """
        Fetch a single unit from cache, or refresh its data from the API and return it.
        """

        if force_fresh or (unit_id not in self._unit_cache):
            _LOGGER.debug(f"Unit {unit_id}: cache miss, fetching")
            unit = await self._fetch_unit_information(unit_id)
            self._unit_cache[unit_id] = unit

        return self._unit_cache[unit_id]

    async def _fetch_unit_information(self, unit_id: int) -> UnitDetails:
        """
        Fetch all metadata for a given unit.
        """

        data = await _make_request(
            self._session,
            "GET",
            f"https://{ZEUS_API_URL}/units/{unit_id}",
            token=await self._auth.get_fresh_token(),
        )
        # _LOGGER.debug(data)

        return {
            "unit_id": unit_id,
            "base": data.get("base", None),
            "front_name": data.get("front_name", None),
            "mac": data.get("mac", None),
            "serial_number": data.get("serial_number", None),
            "package_version": data.get("package_version", None),
            "is_tt_compatible": data.get("is_tt_compatible", False),
            "updated_at": datetime.now().isoformat(),
        }

    async def fetch_scheduled_unit_tests(
        self,
        unit_id: int,
        target_date: str | None = None,
    ) -> ScheduledUnitTests:
        """
        Fetches the most recent measurements for a given unit.
        """
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")

        metric_list = ("httpgetmt", "httppostmt")

        token = await self._auth.get_fresh_token()

        metric_results: ScheduledUnitTests = {
            test["metric_key"]: test
            for test in await asyncio.gather(
                *(
                    self._fetch_scheduled_test_results(
                        unit_id=unit_id,
                        target_date=target_date,
                        metric=metric,
                        token=token,
                    )
                    for metric in metric_list
                )
            )
        }

        results: ScheduledUnitTests = {
            "date": target_date,
            "httpgetmt": metric_results["httpgetmt"],
            "httppostmt": metric_results["httppostmt"],
        }

        return results

    async def _fetch_unit_measurements(
        self,
        unit_id: int,
        target_date: str | None = None,
    ) -> tuple[int, Measurements]:
        return (unit_id, await self.fetch_scheduled_unit_tests(unit_id, target_date))

    async def _fetch_scheduled_test_results(
        self,
        *,
        unit_id: int,
        target_date: str,
        metric: str,
        token: str,
    ) -> ScheduledTests:
        """
        Fetch the results of /scheduled_tests_daily, sorted descending by time
        """
        api_url = UNIT_ANALYTICS_API._replace(
            path=f"{unit_id}/scheduled_tests_daily",
            query=urllib.parse.urlencode(
                {
                    "date": target_date,
                    "metric": metric,
                }
            ),
        ).geturl()

        data = await _make_request(
            self._session,
            "GET",
            api_url,
            token=token,
        )
        results = [
            *reversed(
                sorted(
                    [
                        self._parse_scheduled_test_result(result_data, target_date)
                        for result_data in data["results"]
                    ],
                    key=lambda result: result["timestamp"],
                )
            )
        ]

        return ScheduledTests(
            metric_key=metric,
            results=results,
            metric_unit=data["metricMetadata"]["metricUnit"],
            total_bytes_processed=data["dataUsage"]["totalBytesProcessed"],
        )

    def _parse_scheduled_test_result(
        self,
        data: dict,
        target_date: str,
    ) -> ScheduledTestResult:
        """
        Parse a single entry in the results of /scheduled_tests_daily
        """
        result_time = data["time"]
        return {
            "timestamp": datetime.strptime(
                f"{target_date} {result_time}", "%Y-%m-%d %H:%M:%S"
            ),
            "value": data["metricValue"],
            "target": data["target"],
        }
