from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from PortPilot.documents.classifier import classify_document
from PortPilot.documents.extractor import extract_document
from PortPilot.documents.parser import extract_text_from_pdf
from PortPilot.documents.validator import validate_extracted_document


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...)
):
    """
    Upload and process a maritime document.
    """

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No filename provided.",
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are currently supported.",
        )

    file_id = str(uuid4())

    file_path = UPLOAD_DIR / f"{file_id}.pdf"

    contents = await file.read()

    with open(file_path, "wb") as output:
        output.write(contents)

    # --------------------------------
    # 1. Extract text
    # --------------------------------

    text = extract_text_from_pdf(
        str(file_path)
    )

    if not text:
        return {
            "status": "OCR_REQUIRED",
            "message": (
                "No text could be extracted from "
                "the PDF. It may be a scanned document."
            ),
        }

    # --------------------------------
    # 2. Classify document
    # --------------------------------

    document_type = classify_document(text)

    # --------------------------------
    # 3. Extract fields
    # --------------------------------

    document = extract_document(
        text,
        document_type,
    )

    # --------------------------------
    # 4. Validate fields
    # --------------------------------

    validation_errors = validate_extracted_document(
        document
    )

    # --------------------------------
    # 5. Return result
    # --------------------------------

    return {
        "status": (
            "VALIDATION_ERROR"
            if validation_errors
            else "PROCESSED"
        ),
        "document": document.model_dump(),
        "validation_errors": validation_errors,
    }