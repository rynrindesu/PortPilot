# import re

# from PortPilot.models.documents import (
#     ExtractedDocument,
#     ExtractedField,
# )


# def find_value(pattern: str, text: str):
#     match = re.search(
#         pattern,
#         text,
#         re.IGNORECASE,
#     )

#     if match:
#         return match.group(1).strip()

#     return None


# def extract_document(
#     text: str,
#     document_type: str,
# ) -> ExtractedDocument:

#     vessel_name = find_value(
#         r"vessel\s+name\s*[:\-]\s*(.+)",
#         text,
#     )

#     imo_number = find_value(
#         r"imo\s+(?:number|no\.?)\s*[:\-]\s*(\d+)",
#         text,
#     )

#     call_sign = find_value(
#         r"call\s+sign\s*[:\-]\s*(.+)",
#         text,
#     )

#     gross_tonnage = find_value(
#         r"gross\s+tonnage\s*[:\-]\s*([\d,]+(?:\.\d+)?)",
#         text,
#     )

#     flag = find_value(
#         r"(?:flag|flag state)\s*[:\-]\s*(.+)",
#         text,
#     )

#     return ExtractedDocument(
#         document_type=document_type,

#         vessel_name=(
#             ExtractedField(
#                 value=vessel_name,
#                 confidence=0.90,
#                 source_text=vessel_name,
#             )
#             if vessel_name
#             else None
#         ),

#         imo_number=(
#             ExtractedField(
#                 value=imo_number,
#                 confidence=0.95,
#                 source_text=imo_number,
#             )
#             if imo_number
#             else None
#         ),

#         call_sign=(
#             ExtractedField(
#                 value=call_sign,
#                 confidence=0.90,
#                 source_text=call_sign,
#             )
#             if call_sign
#             else None
#         ),

#         gross_tonnage=(
#             ExtractedField(
#                 value=float(gross_tonnage.replace(",", "")),
#                 confidence=0.95,
#                 source_text=gross_tonnage,
#             )
#             if gross_tonnage
#             else None
#         ),

#         flag=(
#             ExtractedField(
#                 value=flag,
#                 confidence=0.90,
#                 source_text=flag,
#             )
#             if flag
#             else None
#         ),
#     )

import json
import os

from openai import OpenAI

from PortPilot.models.documents import (
    ExtractedDocument,
    ExtractedField,
)


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def extract_document(
    text: str,
    document_type: str,
) -> ExtractedDocument:

    prompt = f"""
You are a maritime document information extraction system.

Document type:
{document_type}

Extract information ONLY when it is explicitly present
in the document.

Do NOT guess missing information.

If a field is not present, return null.

For every extracted field provide:

- value
- confidence between 0 and 1
- source_text containing the relevant text from the document

Potential fields:

- vessel_name
- imo_number
- call_sign
- gross_tonnage
- flag
- issue_date
- expiry_date
- issuing_authority

DOCUMENT:

{text}
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt,
    )

    raw_output = response.output_text

    data = json.loads(raw_output)

    return ExtractedDocument(
        document_type=document_type,
        **data,
    )