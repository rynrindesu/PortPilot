import re

from PortPilot.models.documents import (
    ExtractedDocument,
    ExtractedField,
)


def find_value(pattern: str, text: str):
    match = re.search(
        pattern,
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return None


def extract_document(
    text: str,
    document_type: str,
) -> ExtractedDocument:

    vessel_name = find_value(
        r"vessel\s+name\s*[:\-]\s*(.+)",
        text,
    )

    imo_number = find_value(
        r"imo\s+(?:number|no\.?)\s*[:\-]\s*(\d+)",
        text,
    )

    call_sign = find_value(
        r"call\s+sign\s*[:\-]\s*(.+)",
        text,
    )

    gross_tonnage = find_value(
        r"gross\s+tonnage\s*[:\-]\s*([\d,]+(?:\.\d+)?)",
        text,
    )

    flag = find_value(
        r"(?:flag|flag state)\s*[:\-]\s*(.+)",
        text,
    )

    return ExtractedDocument(
        document_type=document_type,

        vessel_name=(
            ExtractedField(
                value=vessel_name,
                confidence=0.90,
                source_text=vessel_name,
            )
            if vessel_name
            else None
        ),

        imo_number=(
            ExtractedField(
                value=imo_number,
                confidence=0.95,
                source_text=imo_number,
            )
            if imo_number
            else None
        ),

        call_sign=(
            ExtractedField(
                value=call_sign,
                confidence=0.90,
                source_text=call_sign,
            )
            if call_sign
            else None
        ),

        gross_tonnage=(
            ExtractedField(
                value=float(gross_tonnage.replace(",", "")),
                confidence=0.95,
                source_text=gross_tonnage,
            )
            if gross_tonnage
            else None
        ),

        flag=(
            ExtractedField(
                value=flag,
                confidence=0.90,
                source_text=flag,
            )
            if flag
            else None
        ),
    )