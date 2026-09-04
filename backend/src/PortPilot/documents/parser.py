import fitz


def extract_text_from_pdf(file_path: str) -> tuple[str, str]:
    """
    Extract text from a PDF.

    Returns:
        tuple[str, str]:
            - extracted text
            - extraction method
    """

    document = fitz.open(file_path)

    extracted_text = ""

    for page in document:
        extracted_text += page.get_text()

    document.close()

    if extracted_text.strip():
        return extracted_text.strip(), "pdf_text"

    return "", "ocr_required"