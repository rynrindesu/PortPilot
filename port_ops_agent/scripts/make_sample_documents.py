"""Generate synthetic maritime PDFs for exercising the real extraction service.

These are NOT real vessel paperwork. They are plausibly formatted stand-ins,
built from vessels actually present in the PortPilot database, so the OCR and
extraction path can be demonstrated end to end without publishing anyone's
genuine certificates.

    python scripts/make_sample_documents.py

Writes into scripts/sample_documents/.
"""

import argparse
from pathlib import Path

import fitz  # PyMuPDF, already a dependency of the extraction service


OUT_DIR = Path(__file__).resolve().parent / "sample_documents"

PAGE_W, PAGE_H = 595, 842  # A4 at 72 dpi
MARGIN = 56


def _page(doc, title, subtitle):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = MARGIN

    page.insert_text((MARGIN, y), "MARITIME AND PORT AUTHORITY", fontname="hebo", fontsize=9)
    y += 14
    page.insert_text((MARGIN, y), "PORT OF SINGAPORE", fontname="helv", fontsize=8)
    y += 26

    page.draw_line(fitz.Point(MARGIN, y), fitz.Point(PAGE_W - MARGIN, y))
    y += 24

    page.insert_text((MARGIN, y), title, fontname="hebo", fontsize=15)
    y += 18
    page.insert_text((MARGIN, y), subtitle, fontname="helv", fontsize=9)
    y += 30
    return page, y


def _rows(page, y, rows, label_w=190):
    for label, value in rows:
        page.insert_text((MARGIN, y), f"{label}", fontname="helv", fontsize=9.5)
        page.insert_text(
            (MARGIN + label_w, y), str(value), fontname="hebo", fontsize=9.5
        )
        y += 19
    return y


def _footer(page, text):
    page.insert_text(
        (MARGIN, PAGE_H - MARGIN),
        text,
        fontname="helv",
        fontsize=7.5,
    )


def certificate_of_registry(v):
    doc = fitz.open()
    page, y = _page(
        doc,
        "CERTIFICATE OF REGISTRY",
        "Issued under the Merchant Shipping Act",
    )
    y = _rows(
        page,
        y,
        [
            ("Name of Ship", v["vessel_name"]),
            ("IMO Number", v["imo_number"]),
            ("Call Sign", v["call_sign"]),
            ("Flag", v["flag"]),
            ("Port of Registry", "Singapore"),
            ("Official Number", v["official_number"]),
            ("Gross Tonnage", v["gross_tonnage"]),
            ("Net Tonnage", v["net_tonnage"]),
            ("Type of Ship", v["vessel_type"]),
            ("Year of Build", v["year_built"]),
            ("Registered Owner", v["owner"]),
            ("Date of Issue", v["issue_date"]),
            ("Issuing Authority", "Maritime and Port Authority of Singapore"),
        ],
    )
    _footer(page, "SYNTHETIC SAMPLE - generated for PortPilot testing. Not a genuine certificate.")
    return doc


def arrival_general_declaration(v):
    doc = fitz.open()
    page, y = _page(
        doc,
        "ARRIVAL GENERAL DECLARATION",
        "IMO FAL Form 1 - to be lodged on arrival",
    )
    y = _rows(
        page,
        y,
        [
            ("Name of Ship", v["vessel_name"]),
            ("IMO Number", v["imo_number"]),
            ("Call Sign", v.get("call_sign_declared", v["call_sign"])),
            ("Flag State of Ship", v["flag"]),
            ("Type of Ship", v["vessel_type"]),
            ("Gross Tonnage", v["gross_tonnage"]),
            ("Port of Arrival", "Singapore"),
            ("Date and Time of Arrival", v["arrival"]),
            ("Last Port of Call", v["last_port"]),
            ("Next Port of Call", v["next_port"]),
            ("Purpose of Call", v["purpose"]),
            ("Master", v["master"]),
            ("Number of Crew", v["crew"]),
            ("Number of Passengers", v["passengers"]),
            ("Brief Particulars of Cargo", v["cargo"]),
        ],
    )
    _footer(page, "SYNTHETIC SAMPLE - generated for PortPilot testing. Not a genuine declaration.")
    return doc


def crew_list(v):
    doc = fitz.open()
    page, y = _page(doc, "CREW LIST", "IMO FAL Form 5")
    y = _rows(
        page,
        y,
        [
            ("Name of Ship", v["vessel_name"]),
            ("IMO Number", v["imo_number"]),
            ("Call Sign", v["call_sign"]),
            ("Flag", v["flag"]),
            ("Port of Arrival", "Singapore"),
            ("Master", v["master"]),
            ("Number of Crew", v["crew"]),
        ],
    )
    y += 10
    page.insert_text((MARGIN, y), "No.  Family name, given names        Rank        Nationality", fontname="hebo", fontsize=8.5)
    y += 16
    for i, (name, rank, nat) in enumerate(v["crew_rows"], start=1):
        page.insert_text(
            (MARGIN, y),
            f"{i:<4} {name:<32} {rank:<12} {nat}",
            fontname="helv",
            fontsize=8.5,
        )
        y += 13
    _footer(page, "SYNTHETIC SAMPLE - generated for PortPilot testing.")
    return doc


def cargo_declaration(v):
    doc = fitz.open()
    page, y = _page(doc, "CARGO DECLARATION", "IMO FAL Form 2")
    y = _rows(
        page,
        y,
        [
            ("Name of Ship", v["vessel_name"]),
            ("IMO Number", v["imo_number"]),
            ("Call Sign", v["call_sign"]),
            ("Port of Loading", v["last_port"]),
            ("Port of Discharge", "Singapore"),
            ("Total Cargo", v["cargo"]),
            ("Dangerous Goods On Board", v["dg"]),
        ],
    )
    _footer(page, "SYNTHETIC SAMPLE - generated for PortPilot testing.")
    return doc


def maritime_declaration_of_health(v):
    doc = fitz.open()
    page, y = _page(
        doc,
        "MARITIME DECLARATION OF HEALTH",
        "To be completed by the Master on arrival",
    )
    y = _rows(
        page,
        y,
        [
            ("Name of Ship", v["vessel_name"]),
            ("IMO Number", v["imo_number"]),
            ("Flag", v["flag"]),
            ("Port of Arrival", "Singapore"),
            ("Master", v["master"]),
            ("Number of Crew", v["crew"]),
            ("Number of Passengers", v["passengers"]),
            ("Any case of illness on board", "No"),
            ("Valid Ship Sanitation Certificate", v["sanitation"]),
        ],
    )
    _footer(page, "SYNTHETIC SAMPLE - generated for PortPilot testing.")
    return doc


BUILDERS = {
    "certificate_of_registry": certificate_of_registry,
    "arrival_general_declaration": arrival_general_declaration,
    "crew_list": crew_list,
    "cargo_declaration": cargo_declaration,
    "maritime_declaration_of_health": maritime_declaration_of_health,
}


def build_for(vessel: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = vessel["vessel_name"].lower().replace(" ", "_")
    written = []
    for name, builder in BUILDERS.items():
        doc = builder(vessel)
        path = out_dir / f"{slug}__{name}.pdf"
        doc.save(str(path))
        doc.close()
        written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sample_vessels import SAMPLE_VESSELS

    out = Path(args.out)
    total = []
    for vessel in SAMPLE_VESSELS:
        total += build_for(vessel, out)

    print(f"Wrote {len(total)} PDFs to {out}")
    for p in total:
        print("  ", p.name)


if __name__ == "__main__":
    main()
