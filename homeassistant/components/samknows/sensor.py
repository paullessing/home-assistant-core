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

from .const import DOMAIN
from .whitebox import WhiteboxApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""

    api = hass.data[DOMAIN][entry.entry_id]
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

    async_add_entities(
        MetricEntity(coordinator, update.unit.unit_id, metric)
        for update in coordinator.data.values()
        for metric in update.data
    )


class WhitebooxCoordinator(DataUpdateCoordinator[dict[int, UnitUpdate]]):
    """Whitebox coordinator."""

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
        self._unit_device_cache: dict[int, DeviceInfo] = {}

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
                _LOGGER.warning("Listening idx %s", listening_idx)
                data = await self.api.fetch_data()  # (listening_idx)
                _LOGGER.info("Fetched data %s", data)
                return data
        # except ApiAuthError as err:
        #     # Raising ConfigEntryAuthFailed will cancel future updates
        #     # and start a config flow with SOURCE_REAUTH (async_step_reauth)
        #     raise ConfigEntryAuthFailed from err
        # except ApiError as err:
        #     raise UpdateFailed(f"Error communicating with API: {err}")
        finally:
            _LOGGER.warning("Done updating")

    def get_unit_device(self, unit_id: int) -> DeviceInfo:
        if unit_id in self._unit_device_cache:
            return self._unit_device_cache.get(unit_id)

        unit = self.data[unit_id].unit

        device_info = DeviceInfo(
            identifiers={
                # Unique identifier within this domain
                (DOMAIN, unit_id)
            },
            name=f"Whitebox {unit.unit_id}",
            model=f"Whitebox {unit.base}",
            manufacturer="SamKnows",
            sw_version=unit.sw_version,
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

    def __init__(
        self,
        coordinator: WhitebooxCoordinator,
        unit_id: str,
        metric: str,
    ) -> None:
        """Pass coordinator to CoordinatorEntity."""
        _LOGGER.debug("Initialising entity %s", unit_id)
        super().__init__(coordinator, context=unit_id)
        self.unit_id = unit_id
        self.unit = coordinator.data[unit_id].unit
        self.metric = metric

        self._attr_device_class = SensorDeviceClass.DATA_RATE
        self._attr_unique_id = f"whitebox_{unit_id}_{metric}"
        # TODO create a lookup table of metrics -> units
        self._attr_native_unit_of_measurement = "B/s"
        self._attr_suggested_unit_of_measurement = "Mbit/s"
        self._attr_name = metric

        self._attr_native_value = coordinator.data[unit_id].data[metric]

        self._attr_device_info = coordinator.get_unit_device(unit_id)

        _LOGGER.debug("Data is %s %s", metric, self._attr_native_value)
        # _LOGGER.debug("Value %s", self._attr_state)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Coordinator update %s", self.unit_id)
        self._attr_native_value = self.coordinator.data[self.unit_id].data[self.metric]
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
