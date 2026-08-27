import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OCEANX_VESSELS_DUE_TO_ARRIVE_API_KEY")


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

    return vessels