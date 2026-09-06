"""Daily vessel-data lifecycle for Singapore port operations."""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND_DIRECTORY = Path(__file__).resolve().parents[3]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from data.generate_seed_operations import generate_operations

from PortPilot.agent.agent import run_monitoring_cycle
from PortPilot.database.postgres import (
    activate_staged_vessels,
    deactivate_resource_pool,
    delete_vessels_before_operational_date,
    has_operational_assignments,
    stage_vessel_observations,
)
from PortPilot.integration.oceans import get_vessels_due_to_arrive
from PortPilot.monitoring.monitor_service import monitor_vessels, normalize_eta


logger = logging.getLogger(__name__)
SINGAPORE_TIMEZONE = ZoneInfo("Asia/Singapore")


def singapore_now() -> datetime:
    return datetime.now(SINGAPORE_TIMEZONE)


def _upcoming_vessels(vessels, local_now):
    return [
        vessel for vessel in vessels
        if normalize_eta(vessel["eta"]) >= normalize_eta(local_now)
    ]


def _fetch_upcoming_vessels(operating_date, local_now):
    vessels = get_vessels_due_to_arrive(operating_date.isoformat())
    return _upcoming_vessels(vessels, local_now)


def stage_next_day(now: datetime | None = None) -> dict:
    """Fetch tomorrow's vessels and store them without assigning resources."""

    local_now = (now or singapore_now()).astimezone(SINGAPORE_TIMEZONE)
    operating_date = local_now.date() + timedelta(days=1)
    vessels = get_vessels_due_to_arrive(operating_date.isoformat())
    staged_count = stage_vessel_observations(vessels, operating_date)

    result = {
        "job": "stage_next_day",
        "operational_date": operating_date.isoformat(),
        "fetched_vessels": len(vessels),
        "staged_vessels": staged_count,
    }
    logger.info("Next-day staging completed: %s", result)
    return result


def initialize_current_day(now: datetime | None = None) -> dict:
    """Clear prior days and run the original operations initializer once."""

    local_now = (now or singapore_now()).astimezone(SINGAPORE_TIMEZONE)
    operating_date = local_now.date()

    deleted_count = delete_vessels_before_operational_date(operating_date)
    activated_count = activate_staged_vessels(operating_date)
    full_day_vessels = get_vessels_due_to_arrive(operating_date.isoformat())
    deactivated_resources = deactivate_resource_pool()

    # First store the complete midnight feed without assigning from yesterday's
    # resource pool. The original generate_operations() routine then creates
    # operation windows, calculates peak concurrency, builds the pools, and
    # persists all initial allocations in one pass.
    detected_changes = monitor_vessels(
        operating_date.isoformat(),
        current_vessels=full_day_vessels,
        assign_operations=False,
    )
    generated = generate_operations()

    result = {
        "job": "initialize_current_day",
        "operational_date": operating_date.isoformat(),
        "deleted_previous_vessels": deleted_count,
        "activated_staged_vessels": activated_count,
        "deactivated_previous_resources": deactivated_resources,
        "assignments_created": {
            resource_type: len(rows)
            for resource_type, rows in generated.items()
        },
        "detected_changes": detected_changes,
    }
    logger.info("Current-day initialization completed: %s", result)
    return result


def run_hourly_update(now: datetime | None = None) -> dict:
    """Poll today's feed and process ETA changes through the agent pipeline."""

    local_now = (now or singapore_now()).astimezone(SINGAPORE_TIMEZONE)
    operating_date = local_now.date()
    vessels = _fetch_upcoming_vessels(operating_date, local_now)
    result = run_monitoring_cycle(
        operating_date.isoformat(),
        not_before=local_now,
        current_vessels=vessels,
    )
    result = {
        "job": "hourly_update",
        "operational_date": operating_date.isoformat(),
        **result,
    }
    logger.info("Hourly monitoring completed: %s", result)
    return result


def reconcile_on_startup(now: datetime | None = None) -> dict:
    """Restore today's lifecycle safely after an application restart."""

    local_now = (now or singapore_now()).astimezone(SINGAPORE_TIMEZONE)
    operating_date = local_now.date()

    # A restart must not regenerate today's resource pools. Only perform a
    # catch-up initialization when midnight initialization never produced any
    # complete operational assignment for this date.
    if not has_operational_assignments(operating_date):
        return initialize_current_day(local_now)

    deleted_count = delete_vessels_before_operational_date(operating_date)
    activated_count = activate_staged_vessels(operating_date)
    vessels = _fetch_upcoming_vessels(operating_date, local_now)
    pipeline_result = run_monitoring_cycle(
        operating_date.isoformat(),
        not_before=local_now,
        current_vessels=vessels,
    )

    result = {
        "job": "startup_reconciliation",
        "operational_date": operating_date.isoformat(),
        "deleted_previous_vessels": deleted_count,
        "activated_staged_vessels": activated_count,
        **pipeline_result,
    }
    logger.info("Startup reconciliation completed: %s", result)
    return result


def run_startup_catchup(now: datetime | None = None) -> dict:
    """Choose the safe startup job for the current Singapore-local time."""

    local_now = (now or singapore_now()).astimezone(SINGAPORE_TIMEZONE)
    if local_now.hour >= 21:
        staged = stage_next_day(local_now)
        if has_operational_assignments(local_now.date()):
            return staged
        return {
            "job": "startup_catchup",
            "staging": staged,
            "missed_midnight_initialization": reconcile_on_startup(local_now),
        }
    return reconcile_on_startup(local_now)
