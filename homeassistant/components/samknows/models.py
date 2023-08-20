class UnitDetails:
    """Contains information about a specific unit."""

    def __init__(
        self,
        unit_id: int,
        *,
        front_name: str | None = None,
        mac: str | None = None,
        base: str | None = None,
        serial_number: str | None = None,
        package_version: str | None = None,
        is_tt_compatible: bool = False,
        **kwargs,
    ) -> None:
        self.unit_id = unit_id
        self.front_name = front_name
        self.mac_address = mac
        self.base = base
        self.serial_number = serial_number
        self.sw_version = package_version
        self.is_tt_compatible = is_tt_compatible

        self.metrics = {}


class UnitUpdate:
    def __init__(
        self, details: UnitDetails, data: dict[str, str | int | float]
    ) -> None:
        self.unit = details
        self.data = data
