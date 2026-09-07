"""Drive real port calls through the running port-ops service.

Nothing is faked here: every document is uploaded to /documents/upload and
parsed by the real extraction service, and every compliance verdict comes from
/port-calls/{id}/check running the real engine. The script only supplies the
inputs a ship's agent would submit.

The service keeps port calls in memory, so re-run this after restarting it.

    python scripts/seed_port_calls.py
    python scripts/seed_port_calls.py --api http://127.0.0.1:8001
"""

import argparse
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from sample_vessels import SAMPLE_VESSELS  # noqa: E402

DOC_DIR = SCRIPT_DIR / "sample_documents"

# Port-call level facts a ship's agent declares, which are not in the PDFs.
DECLARED = {
    "FAIRWAY": {
        "port_call_id": "SGSIN-2601",
        "first_singapore_call": False,
        "purpose_of_call": "cargo",
        "carrying_dangerous_goods": False,
        "radioactive_material": False,
    },
    "MARLIN SATU": {
        "port_call_id": "SGSIN-2602",
        "first_singapore_call": False,
        "purpose_of_call": "cargo",
        "carrying_dangerous_goods": False,
        "radioactive_material": False,
    },
    "BAY PEACE": {
        "port_call_id": "SGSIN-2603",
        "first_singapore_call": True,
        "purpose_of_call": "cargo",
        "carrying_dangerous_goods": True,
        "radioactive_material": False,
    },
}


def upload(api: str, path: Path) -> dict | None:
    """Push one PDF through the real extraction service."""

    with open(path, "rb") as handle:
        response = requests.post(
            f"{api}/documents/upload",
            files={"file": (path.name, handle, "application/pdf")},
            timeout=300,
        )
    response.raise_for_status()
    payload = response.json()

    if payload.get("status") == "OCR_REQUIRED":
        print(f"    {path.name}: no text layer, OCR required")
        return None

    document = payload.get("document")
    if document is None:
        print(f"    {path.name}: no document returned ({payload.get('status')})")
        return None

    extracted = sum(
        1
        for value in document.values()
        if isinstance(value, dict) and value.get("value") is not None
    )
    print(f"    {path.name}: {document.get('document_type')} · {extracted} fields")
    return document


def seed_vessel(api: str, vessel: dict) -> None:
    declared = DECLARED[vessel["vessel_name"]]
    port_call_id = declared["port_call_id"]
    slug = vessel["vessel_name"].lower().replace(" ", "_")

    print(f"\n{port_call_id}  {vessel['vessel_name']}")

    documents = []
    for path in sorted(DOC_DIR.glob(f"{slug}__*.pdf")):
        document = upload(api, path)
        if document is not None:
            documents.append(document)

    if not documents:
        print("  no documents extracted; skipping")
        return

    created = requests.post(
        f"{api}/port-calls",
        json={
            "port_call_id": port_call_id,
            "vessel_name": vessel["vessel_name"],
            "imo_number": vessel["imo_number"],
            "call_sign": vessel["call_sign"],
            "first_singapore_call": declared["first_singapore_call"],
            "purpose_of_call": declared["purpose_of_call"],
            "carrying_dangerous_goods": declared["carrying_dangerous_goods"],
            "radioactive_material": declared["radioactive_material"],
        },
        timeout=60,
    )
    if created.status_code == 409:
        print("  port call already exists; reusing")
    else:
        created.raise_for_status()

    submitted = requests.post(
        f"{api}/port-calls/{port_call_id}/documents",
        json=documents,
        timeout=120,
    )
    submitted.raise_for_status()
    print(f"  submitted {submitted.json()['document_count']} documents")

    checked = requests.post(f"{api}/port-calls/{port_call_id}/check", timeout=300)
    checked.raise_for_status()
    result = checked.json()

    compliance = result["compliance"]
    risk = result["risk"]
    print(f"  compliance : {compliance['status']}")
    for issue in compliance["issues"]:
        print(f"      {issue['code']}: {issue['message'][:88]}")
    print(f"  risk       : {risk['risk_score']} ({risk['risk_level']})")
    for factor in risk["risk_factors"]:
        print(f"      {factor}")
    print(f"  inspection : {result['inspection']['decision']}")
    print(f"  escalation : {result['escalation']['action']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    args = parser.parse_args()

    if not DOC_DIR.exists():
        raise SystemExit(
            "No sample documents. Run scripts/make_sample_documents.py first."
        )

    for vessel in SAMPLE_VESSELS:
        seed_vessel(args.api, vessel)

    listed = requests.get(f"{args.api}/port-calls", timeout=60).json()
    print(f"\n{len(listed)} port call(s) now held by the service.")


if __name__ == "__main__":
    main()
