import os
import logging
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OCEANX_VESSELS_DUE_TO_ARRIVE_API_KEY")
logger = logging.getLogger(__name__)


def _eta_for_comparison(value):
    eta = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if eta.tzinfo is None:
        eta = eta.replace(tzinfo=timezone.utc)
    return eta.astimezone(timezone.utc)


def _deduplicate_vessels_by_latest_eta(vessels):
    """Return one API record per vessel, keeping its latest ETA."""

    latest_by_vessel = {}
    duplicate_count = 0

    for vessel in vessels:
        key = (vessel["vessel_name"], vessel["imo_number"])
        existing = latest_by_vessel.get(key)

        if existing is None:
            latest_by_vessel[key] = vessel
            continue

        duplicate_count += 1
        if _eta_for_comparison(vessel["eta"]) > _eta_for_comparison(existing["eta"]):
            latest_by_vessel[key] = vessel

    if duplicate_count:
        logger.info(
            "Collapsed %s duplicate OCEANS-X vessel record(s), keeping the "
            "latest ETA for each vessel.",
            duplicate_count,
        )

    return list(latest_by_vessel.values())


def get_vessels_due_to_arrive(date):
    """
    Retrieves vessels scheduled to arrive at the Port of Singapore
    for a specified date using the OCEANS-X API.

    Args:
        date (str): The arrival date in YYYY-MM-DD format.

    Returns:
        list: A list of dictionaries containing vessel particulars,
              expected arrival time, origin, and destination.
    """
    
    url = f"https://oceans-x.mpa.gov.sg/api/v1/vessel/duetoarrive/1.0.0/date/{date}"

    headers = {
            "accept": "application/json",
            "ApiKey": API_KEY
    }

    response = requests.get(
        url,
        headers=headers
    )

    response.raise_for_status()

    data = response.json()

    vessels = []

    for vessel in data:
        particulars = vessel["vesselParticulars"]

        vessels.append({
            "vessel_name": particulars["vesselName"],
            "call_sign": particulars["callSign"],
            "imo_number": particulars["imoNumber"],
            "flag": particulars["flag"],
            "eta": vessel["duetoArriveTime"],
            "location_from": vessel["locationFrom"],
            "location_to": vessel["locationTo"]
        })

    return _deduplicate_vessels_by_latest_eta(vessels)
