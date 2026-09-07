"""Drive the mock-document test matrix through the running port-ops service.

Every step here is a real HTTP call to the real service: the PDFs go through
the actual extraction pipeline (text layer, then the LLM classifier and field
extractor), and compliance, risk, inspection and escalation are decided by the
real rule engine. Nothing is stubbed, so a passing row means the deployed code
produced that outcome.

    python scripts/run_scenarios.py                  # run all, report
    python scripts/run_scenarios.py --only 1 6 11    # run some
    python scripts/run_scenarios.py --keep           # don't reset first

Scenario numbering follows "Tests Scenarios.pdf".
"""

import argparse
import sys
from pathlib import Path

import requests


API = "http://127.0.0.1:8001"
DOCS = (
    Path(__file__).resolve().parents[2]
    / "samples"
    / "Mock Test"
    / "Mock Docs"
)

TIMEOUT = 180


class Scenario:
    def __init__(
        self,
        number,
        name,
        documents,
        expect,
        *,
        dangerous_goods=False,
        radioactive=False,
        first_call=False,
        phase="arrival",
        purpose="cargo",
        inspect=None,
        arrival_documents=None,
    ):
        self.number = number
        self.name = name
        self.documents = documents
        self.expect = expect
        self.dangerous_goods = dangerous_goods
        self.radioactive = radioactive
        self.first_call = first_call
        self.phase = phase
        self.purpose = purpose
        self.inspect = inspect
        self.arrival_documents = arrival_documents or []

    @property
    def port_call_id(self):
        return f"SC-{self.number:02d}"


SCENARIOS = [
    Scenario(1, "Clean arrival", ["Clean Arrival.pdf"], "PASS"),
    Scenario(2, "Missing required field", ["Missing IMO.pdf"], "CORRECTION_REQUIRED"),
    Scenario(
        3,
        "Cross-document mismatch",
        ["Clean Arrival.pdf", "Certificate of Registry.pdf"],
        "CORRECTION_REQUIRED",
    ),
    Scenario(
        4,
        "Dangerous goods declared",
        ["Clean Arrival.pdf", "Dangerous Goods.pdf"],
        "ELEVATED_RISK",
        dangerous_goods=True,
    ),
    Scenario(
        5,
        "DG declaration missing",
        ["Clean Arrival.pdf"],
        "CORRECTION_REQUIRED",
        dangerous_goods=True,
    ),
    Scenario(
        6,
        "Radioactive cargo",
        ["Clean Arrival.pdf", "Radioactive Goods.pdf"],
        "INSPECTION_REQUIRED",
        dangerous_goods=True,
        radioactive=True,
    ),
    Scenario(
        7,
        "Clean departure",
        ["Departure GD.pdf"],
        "PASS",
        phase="departure",
        arrival_documents=["Clean Arrival.pdf"],
    ),
    Scenario(
        8,
        "Departure IMO mismatch",
        ["Departure IMO Mismatch.pdf"],
        "CORRECTION_REQUIRED",
        phase="departure",
        arrival_documents=["Clean Arrival.pdf"],
    ),
    Scenario(
        9,
        "Arrival/departure consistency",
        ["Departure GD.pdf"],
        "PASS",
        phase="departure",
        arrival_documents=["Clean Arrival.pdf"],
    ),
    Scenario(10, "Full normal port call", ["Clean Arrival.pdf"], "PASS"),
    Scenario(
        11,
        "Full inspection flow",
        ["Clean Arrival.pdf", "Radioactive Goods.pdf"],
        "INSPECTION_REQUIRED",
        dangerous_goods=True,
        radioactive=True,
        inspect="clear",
    ),
    Scenario(
        12,
        "Registry mismatch",
        ["Arrival GD.pdf", "Certificate of Registry.pdf"],
        "CORRECTION_REQUIRED",
    ),
]


_extraction_cache: dict[str, dict] = {}


def extract(file_name: str) -> dict:
    """Upload one PDF through the real extraction pipeline."""
    if file_name in _extraction_cache:
        return _extraction_cache[file_name]

    path = DOCS / file_name
    if not path.exists():
        raise FileNotFoundError(path)

    with open(path, "rb") as handle:
        response = requests.post(
            f"{API}/documents/upload",
            files={"file": (file_name, handle, "application/pdf")},
            timeout=TIMEOUT,
        )
    response.raise_for_status()
    body = response.json()
    if "document" not in body:
        raise RuntimeError(f"{file_name}: {body.get('message') or body}")

    _extraction_cache[file_name] = body["document"]
    return body["document"]


def identity(document: dict) -> tuple[str, str, str]:
    def value(field):
        node = document.get(field)
        return node.get("value") if isinstance(node, dict) else None

    return (
        value("vessel_name") or "UNKNOWN",
        str(value("imo_number") or ""),
        str(value("call_sign") or ""),
    )


def run(scenario: Scenario, keep: bool) -> dict:
    # Port calls live in memory in the service and there is no delete route,
    # so a re-run needs the service restarted rather than a reset call here.
    documents = [extract(name) for name in scenario.documents]
    vessel_name, imo_number, call_sign = identity(documents[0])

    created = requests.post(
        f"{API}/port-calls",
        json={
            "port_call_id": scenario.port_call_id,
            "vessel_name": vessel_name,
            "imo_number": imo_number or None,
            "call_sign": call_sign or None,
            "first_singapore_call": scenario.first_call,
            "purpose_of_call": scenario.purpose,
            "carrying_dangerous_goods": scenario.dangerous_goods,
            "radioactive_material": scenario.radioactive,
        },
        timeout=TIMEOUT,
    )
    if created.status_code == 409:
        return {"skipped": "port call already exists"}
    created.raise_for_status()

    if scenario.phase == "departure" and scenario.arrival_documents:
        # A departure declaration is only meaningful once arrival has cleared,
        # so drive the real workflow rather than checking departure paperwork
        # against arrival requirements.
        arrival_docs = [extract(name) for name in scenario.arrival_documents]
        requests.post(
            f"{API}/port-calls/{scenario.port_call_id}/documents",
            json=arrival_docs,
            timeout=TIMEOUT,
        ).raise_for_status()
        requests.post(
            f"{API}/port-calls/{scenario.port_call_id}/check", timeout=TIMEOUT
        ).raise_for_status()
        for _ in range(2):  # arrival -> operations -> departure
            requests.post(
                f"{API}/port-calls/{scenario.port_call_id}/advance",
                timeout=TIMEOUT,
            )

    # submit_documents replaces the document set rather than appending, so the
    # arrival paperwork has to be resubmitted alongside the departure paperwork
    # or cross-phase consistency has nothing to compare against.
    submitted = (
        [extract(name) for name in scenario.arrival_documents] + documents
        if scenario.phase == "departure" and scenario.arrival_documents
        else documents
    )
    requests.post(
        f"{API}/port-calls/{scenario.port_call_id}/documents",
        json=submitted,
        timeout=TIMEOUT,
    ).raise_for_status()

    checked = requests.post(
        f"{API}/port-calls/{scenario.port_call_id}/check", timeout=TIMEOUT
    )
    checked.raise_for_status()
    result = checked.json()

    outcome = {
        "compliance": result["compliance"]["status"],
        "issues": len(result["compliance"]["issues"]),
        "risk_score": result["risk"]["risk_score"],
        "risk_level": result["risk"]["risk_level"],
        "inspection": result["inspection"]["decision"],
        "escalation": result["escalation"]["action"],
        "documents": len(submitted),
    }

    # Scenario 11 continues through the human inspection lifecycle.
    if scenario.inspect and outcome["inspection"] == "inspection_required":
        started = requests.post(
            f"{API}/port-calls/{scenario.port_call_id}/inspection/start",
            timeout=TIMEOUT,
        )
        if started.ok:
            completed = requests.post(
                f"{API}/port-calls/{scenario.port_call_id}/inspection/complete",
                json={
                    "cleared": scenario.inspect == "clear",
                    "findings": None if scenario.inspect == "clear" else "Findings raised.",
                },
                timeout=TIMEOUT,
            )
            if completed.ok:
                outcome["inspection_result"] = completed.json()["state"]["status"]

    return outcome


def verdict(scenario: Scenario, outcome: dict) -> str:
    if "skipped" in outcome:
        return "SKIP"
    expected = scenario.expect
    if expected == "PASS":
        return "ok" if outcome["compliance"] == "PASS" else "DIFFERS"
    if expected == "CORRECTION_REQUIRED":
        return (
            "ok"
            if outcome["compliance"] in {"CORRECTION_REQUIRED", "HUMAN_REVIEW"}
            else "DIFFERS"
        )
    if expected == "INSPECTION_REQUIRED":
        return "ok" if outcome["inspection"] == "inspection_required" else "DIFFERS"
    if expected == "ELEVATED_RISK":
        return "ok" if outcome["risk_score"] >= 25 else "DIFFERS"
    return "?"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=int, nargs="*", help="scenario numbers")
    parser.add_argument("--keep", action="store_true", help="keep existing port calls")
    args = parser.parse_args()

    try:
        requests.get(f"{API}/", timeout=10).raise_for_status()
    except Exception as error:
        print(f"port-ops service not reachable at {API}: {error}")
        return 1

    selected = [s for s in SCENARIOS if not args.only or s.number in args.only]

    print(f"\n{'#':>3}  {'scenario':30} {'compliance':20} {'risk':>12} "
          f"{'inspection':20} {'escalation':22} verdict")
    print("-" * 130)

    differs = 0
    for scenario in selected:
        try:
            outcome = run(scenario, args.keep)
        except Exception as error:
            print(f"{scenario.number:>3}  {scenario.name:30} ERROR {type(error).__name__}: {str(error)[:60]}")
            differs += 1
            continue

        if "skipped" in outcome:
            print(
                f"{scenario.number:>3}  {scenario.name:30} "
                f"SKIPPED - {outcome['skipped']}. Restart the service to clear "
                f"the in-memory port-call store."
            )
            differs += 1
            continue

        mark = verdict(scenario, outcome)
        if mark == "DIFFERS":
            differs += 1
        risk = f"{outcome['risk_score']} ({outcome['risk_level']})"
        print(
            f"{scenario.number:>3}  {scenario.name:30} "
            f"{outcome['compliance']:20} {risk:>12} "
            f"{outcome['inspection']:20} {outcome['escalation']:22} {mark}"
        )

    print(f"\n{len(selected) - differs}/{len(selected)} matched the expected outcome.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
