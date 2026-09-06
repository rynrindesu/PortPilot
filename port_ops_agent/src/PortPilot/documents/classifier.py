# DOCUMENT_TYPES = [
#     "certificate_of_registry",
#     "tonnage_certificate",
#     "arrival_general_declaration",
#     "departure_general_declaration",
#     "cargo_manifest",
#     "bill_of_lading",
#     "dangerous_goods_declaration",
#     "unknown",
# ]


# def classify_document(text: str) -> str:
#     """
#     Classify a maritime document based on its text.

#     Returns:
#         str: Document type.
#     """

#     text_lower = text.lower()

#     if (
#         "certificate of registry" in text_lower
#         or "certificate of registration" in text_lower
#     ):
#         return "certificate_of_registry"

#     if (
#         "international tonnage certificate" in text_lower
#         or "tonnage certificate" in text_lower
#     ):
#         return "tonnage_certificate"

#     if (
#         "arrival general declaration" in text_lower
#         or "general declaration of arrival" in text_lower
#     ):
#         return "arrival_general_declaration"

#     if (
#         "departure general declaration" in text_lower
#         or "general declaration of departure" in text_lower
#     ):
#         return "departure_general_declaration"

#     if "cargo manifest" in text_lower:
#         return "cargo_manifest"

#     if "bill of lading" in text_lower:
#         return "bill_of_lading"

#     if (
#         "dangerous goods declaration" in text_lower
#         or "dangerous goods" in text_lower
#     ):
#         return "dangerous_goods_declaration"

#     return "unknown"

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


DOCUMENT_TYPES = [
    "certificate_of_registry",
    "tonnage_certificate",
    "arrival_general_declaration",
    "departure_general_declaration",
    "cargo_manifest",
    "bill_of_lading",
    "dangerous_goods_declaration",
    "unknown",
]


def classify_document(text: str) -> str:

    prompt = f"""
You are a maritime document classification system.

Classify the following document into exactly ONE
of these categories:

{", ".join(DOCUMENT_TYPES)}

Rules:

1. Return only the category name.
2. Do not invent a new category.
3. If the document cannot be confidently classified,
   return "unknown".

DOCUMENT:

{text}
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt,
    )

    result = response.output_text.strip()

    if result not in DOCUMENT_TYPES:
        return "unknown"

    return result