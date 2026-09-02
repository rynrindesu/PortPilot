import fitz
import io

import pytesseract

from PIL import Image


def extract_text_from_pdf(file_path: str) -> tuple[str, str]:
    """
    Returns:
        (text, extraction_method)
    """

    document = fitz.open(file_path)

    extracted_text = ""

    for page in document:
        extracted_text += page.get_text()

    document.close()

    if extracted_text.strip():
        return extracted_text.strip(), "pdf_text"

    text = extract_text_with_ocr(file_path)

    return text, "ocr"


def extract_text_with_ocr(file_path: str) -> str:

    document = fitz.open(file_path)

    extracted_text = ""

    for page in document:

        pix = page.get_pixmap(
            matrix=fitz.Matrix(2, 2)
        )

        image_bytes = pix.tobytes("png")

        image = Image.open(
            io.BytesIO(image_bytes)
        )

        text = pytesseract.image_to_string(image)

        extracted_text += text + "\n"

    document.close()

    return extracted_text.strip()