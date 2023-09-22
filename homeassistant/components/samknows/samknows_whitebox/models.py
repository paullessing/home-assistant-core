from typing import TypedDict
from datetime import datetime

# from typing import NotRequired


class UnitDetails(TypedDict):
    """
    Contains information about a specific unit.
    """

    unit_id: int
    front_name: str | None
    mac: str | None
    base: str | None
    serial_number: str | None
    package_version: str | None
    is_tt_compatible: bool
    updated_at: str


class Measurement(TypedDict):
    """
    A single measurement of a metric.
    """

    value: float | int
    timestamp: datetime


class MetricData(TypedDict):
    """
    A set of measurements for a metric.
    """

    avg_value: Measurement  # TODO
    history: list[Measurement]


class Measurements(TypedDict):
    """
    Collection of all supported metrics and their data.
    """

    httpgetmt: MetricData
    httppostmt: MetricData


class ScheduledTestResult(TypedDict):
    timestamp: str
    target: str
    value: int


class ScheduledTests(TypedDict):
    metric_key: str
    metric_unit: str
    total_bytes_processed: int
    results: list[ScheduledTestResult]


class ScheduledUnitTests(TypedDict):
    date: str
    httpgetmt: ScheduledTests
    httppostmt: ScheduledTests


class UnitUpdate(TypedDict):
    """
    Parent type for each unit, containing unit data as well as current measurements.
    """

    unit: UnitDetails
    measurements: Measurements
