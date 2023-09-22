import asyncio
from datetime import timedelta
import logging

import async_timeout

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.const import UnitOfDataRate

from .const import DOMAIN
from .samknows_whitebox import (
    WhiteboxApi,
    UnitDetails,
    ScheduledUnitTests,
    ScheduledTests,
    ScheduledTestResult,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""

    api: WhiteboxApi = hass.data[DOMAIN][entry.entry_id]
    # entities = []

    # assuming API object stored here by __init__.py

    # entities.append(SensorEntity())
    coordinator = WhitebooxCoordinator(hass, api)

    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    # If you do not want to retry setup on failure, use
    # coordinator.async_refresh() instead
    #
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info("Coordinator has run %s", coordinator.data)

    entities = [
        MetricEntity(coordinator, unit_id, metric)
        for unit_id in coordinator.data.units.keys()
        for metric in ("httpgetmt", "httppostmt")
    ]

    _LOGGER.debug("Entities %s", entities)

    async_add_entities(
        MetricEntity(coordinator, unit_id, metric)
        for unit_id in coordinator.data.units.keys()
        for metric in ("httpgetmt", "httppostmt")
    )


class WhiteboxUnitData:
    details: UnitDetails
    latest_tests: ScheduledUnitTests | None

    def __init__(
        self,
        details: UnitDetails,
        latest_tests: ScheduledUnitTests = None,
    ) -> None:
        self.details = details
        self.latest_tests = latest_tests


class WhiteboxData:
    units: dict[int, WhiteboxUnitData]

    def __init__(self, units: dict[int, WhiteboxUnitData] | None = None) -> None:
        if units is None:
            units = {}
        self.units = units


class WhitebooxCoordinator(DataUpdateCoordinator[WhiteboxData]):
    """Whitebox coordinator."""

    api: WhiteboxApi
    _unit_device_cache: dict[int, DeviceInfo]

    def __init__(self, hass: HomeAssistant, api: WhiteboxApi) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Whitebox",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=300),
        )
        self.api = api
        self._unit_device_cache = {}

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                # Grab active context variables to limit data required to be fetched from API
                # Note: using context is not required if there is no need or ability to limit
                # data retrieved from API.
                listening_idx = set(self.async_contexts())
                _LOGGER.warning("Listening idx %s", [*listening_idx])

                # TODO only fetch for unit IDs in listening_idx
                unit_details = await self.api.fetch_user_units()
                # units = [WhiteboxUnitData(details) for details in unit_details]

                unit_data: list[WhiteboxUnitData] = await asyncio.gather(
                    *(self._get_whitebox_unit_data(details) for details in unit_details)
                )

                data = {
                    unit_info.details["unit_id"]: unit_info for unit_info in unit_data
                }

                # data = await self.api.fetch_data()  # (listening_idx)
                _LOGGER.info("Fetched data %s", data)
                return WhiteboxData(data)

            # TODO: Deal with different ways that the API Auth can fail
            # Raise correct errors, and handle them here

        # except ApiAuthError as err:
        #     # Raising ConfigEntryAuthFailed will cancel future updates
        #     # and start a config flow with SOURCE_REAUTH (async_step_reauth)
        #     raise ConfigEntryAuthFailed from err
        # except ApiError as err:
        #     raise UpdateFailed(f"Error communicating with API: {err}")
        finally:
            _LOGGER.warning("Done updating")

    async def _get_whitebox_unit_data(self, details: UnitDetails) -> WhiteboxData:
        tests = await self.api.fetch_scheduled_unit_tests(details["unit_id"])

        return WhiteboxUnitData(details, tests)

    def get_unit_device(self, unit_id: int) -> DeviceInfo:
        if unit_id in self._unit_device_cache:
            return self._unit_device_cache.get(unit_id)

        unit = self.data.units[unit_id].details

        device_info = DeviceInfo(
            identifiers={
                # Unique identifier within this domain
                (DOMAIN, unit_id)
            },
            name=f"Whitebox {unit['unit_id']}",
            model=f"Whitebox {unit['base']}",
            manufacturer="SamKnows",
            sw_version=unit["package_version"],
        )
        self._unit_device_cache[unit_id] = device_info

        return device_info


class MetricEntity(CoordinatorEntity[WhitebooxCoordinator], SensorEntity):
    """An entity using CoordinatorEntity.

    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass
      available

    """

    unit: UnitDetails

    def __init__(
        self,
        coordinator: WhitebooxCoordinator,
        unit_id: int,
        metric: str,
    ) -> None:
        """Pass coordinator to CoordinatorEntity."""
        _LOGGER.debug("Initialising entity %s", unit_id)
        super().__init__(coordinator, context=unit_id)
        self.unit_id = unit_id
        self.unit = coordinator.data.units[unit_id].details
        self.metric = metric

        # self.has_entity_name = True

        self._attr_device_class = SensorDeviceClass.DATA_RATE
        self._attr_unique_id = f"whitebox_{unit_id}_{metric}"
        _LOGGER.debug("entity id %s", self._attr_unique_id)
        # TODO create a lookup table of metrics -> units
        self._attr_native_unit_of_measurement = UnitOfDataRate.BITS_PER_SECOND
        self._attr_suggested_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
        self._attr_name = self._get_metric_name(metric)
        self._attr_suggested_display_precision = 2

        test_data = self._get_test_data(
            metric, coordinator.data.units[unit_id].latest_tests
        )

        test_result = self._get_latest_result(test_data)

        if test_result is None:
            value = None
        else:
            value = test_result["value"]

        self._attr_native_value = value

        self._attr_device_info = coordinator.get_unit_device(unit_id)

        _LOGGER.debug("Data is %s %s", metric, self._attr_native_value)
        # _LOGGER.debug("Value %s", self._attr_state)

    def _get_test_data(
        self, metric: str, data: ScheduledUnitTests | None
    ) -> ScheduledTests | None:
        if data is None:
            return None

        test_data: ScheduledTests | None = data.get(metric)
        if test_data is None:
            return None

        return test_data

    def _get_latest_result(
        self, test_data: ScheduledTests
    ) -> ScheduledTestResult | None:
        if test_data is None:
            return None
        if len(test_data["results"]) == 0:
            return None
        return test_data["results"][0]

    def _get_metric_name(self, metric: str) -> str:
        match metric:
            case "httpgetmt":
                return "Download Speed"
            case "httppostmt":
                return "Upload Speed"
            case _:
                return metric

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Coordinator update %d", self.unit_id)
        if not self.unit_id in self.coordinator.data.units:
            _LOGGER.debug("Unit %s not found in coordinator data", self.unit_id)
            return

        unit = self.coordinator.data.units[self.unit_id]

        if not self.metric in unit.latest_tests:
            _LOGGER.debug("Metric %s not found in latest tests", self.metric)
            return

        test: ScheduledTests = unit.latest_tests[self.metric]

        if len(test["results"]) == 0:
            _LOGGER.debug("Metric %s has no results", self.metric)
            return

        result = test["results"][0]

        self._attr_native_value = result["value"]
        _LOGGER.debug("Updated %s.%s=%s", self.unit_id, self.metric, result["value"])

        self.async_write_ha_state()

    # @property
    # def device_info(
    #     self,
    # ) -> DeviceInfo:  # TODO or just add it as self._attr_device_info
    #     """Return the device info."""
    #     return DeviceInfo(
    #         identifiers={
    #             # Unique identifier within this domain
    #             (DOMAIN, self.unit_id)
    #         },
    #         name=f"Whitebox {self.unit_id}",
    #         manufacturer="SamKnows",
    #         model=f"Whitebox {self.unit.base}",
    #         sw_version=self.unit.sw_version,
    #     )
