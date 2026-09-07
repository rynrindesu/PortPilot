"""Vessel particulars used to build the synthetic sample documents.

The names, IMO numbers and call signs are real vessels drawn from the live
OCEANS-X arrival feed, so the compliance engine's cross-document identity
checks operate on the same identifiers the rescheduling side is working with.
Everything else - tonnage, crew, cargo, owner - is invented, because that
detail is not in the arrival feed and inventing it is preferable to guessing
at a real ship's paperwork.

Three scenarios are covered deliberately:

  1. FAIRWAY        - clean submission, everything agrees.
  2. MARLIN SATU    - call sign disagrees between two documents, so the
                      consistency check raises FIELD_MISMATCH.
  3. BAY PEACE      - dangerous goods declared and a missing sanitation
                      certificate, which drives risk up and inspection on.
"""

SAMPLE_VESSELS = [
    {
        "vessel_name": "FAIRWAY",
        "imo_number": "9132454",
        "call_sign": "9V6621",
        "flag": "Singapore",
        "official_number": "384112",
        "gross_tonnage": "24 918",
        "net_tonnage": "11 640",
        "vessel_type": "Oil Products Tanker",
        "year_built": "2004",
        "owner": "Fairway Shipping Pte Ltd",
        "issue_date": "2021-06-18",
        "arrival": "2026-09-07T14:45",
        "last_port": "Port Klang",
        "next_port": "Hong Kong",
        "purpose": "cargo",
        "master": "R. Tan Wei Ming",
        "crew": "22",
        "passengers": "0",
        "cargo": "12 400 t gas oil",
        "dg": "No",
        "sanitation": "Yes - valid to 2027-01-14",
        "crew_rows": [
            ("TAN WEI MING, R.", "Master", "Singapore"),
            ("SANTOS, M. A.", "Chief Off.", "Philippines"),
            ("KUMAR, V.", "Chief Eng.", "India"),
            ("LIM, J. H.", "Second Off.", "Malaysia"),
            ("REYES, D. P.", "Bosun", "Philippines"),
        ],
    },
    {
        # The call sign here disagrees with the certificate of registry on
        # purpose, so the consistency check has something real to catch.
        "vessel_name": "MARLIN SATU",
        "imo_number": "9675119",
        "call_sign": "9V8143",
        "call_sign_declared": "9V8341",
        "flag": "Singapore",
        "official_number": "401277",
        "gross_tonnage": "8 640",
        "net_tonnage": "3 902",
        "vessel_type": "General Cargo",
        "year_built": "2013",
        "owner": "Marlin Line Pte Ltd",
        "issue_date": "2019-11-02",
        "arrival": "2026-09-07T04:47",
        "last_port": "Jakarta",
        "next_port": "Port Klang",
        "purpose": "cargo",
        "master": "A. Rahman",
        "crew": "17",
        "passengers": "0",
        "cargo": "4 120 t steel coil",
        "dg": "No",
        "sanitation": "Yes - valid to 2026-12-03",
        "crew_rows": [
            ("RAHMAN, A.", "Master", "Malaysia"),
            ("WIJAYA, B.", "Chief Off.", "Indonesia"),
            ("NG, K. S.", "Chief Eng.", "Singapore"),
            ("HASAN, M.", "Oiler", "Bangladesh"),
        ],
    },
    {
        "vessel_name": "BAY PEACE",
        "imo_number": "9952268",
        "call_sign": "9V4407",
        "flag": "Panama",
        "official_number": "512908",
        "gross_tonnage": "41 250",
        "net_tonnage": "19 880",
        "vessel_type": "Chemical Tanker",
        "year_built": "2018",
        "owner": "Bay Peace Maritime SA",
        "issue_date": "2022-02-27",
        "arrival": "2026-09-07T06:00",
        "last_port": "Jubail",
        "next_port": "Kaohsiung",
        "purpose": "cargo",
        "master": "S. Petrov",
        "crew": "24",
        "passengers": "0",
        "cargo": "IMDG Class 3 - 9 800 t",
        "dg": "Yes - IMDG Class 3",
        "sanitation": "No - expired 2026-08-19",
        "crew_rows": [
            ("PETROV, S.", "Master", "Bulgaria"),
            ("ANDERSEN, L.", "Chief Off.", "Denmark"),
            ("GOMEZ, R.", "Chief Eng.", "Philippines"),
            ("ILIC, N.", "Pumpman", "Serbia"),
        ],
    },
]
