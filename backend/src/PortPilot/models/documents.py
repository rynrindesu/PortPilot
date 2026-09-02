from typing import Optional, Union

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    value: Optional[Union[str, float]] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_text: Optional[str] = None


class ExtractedDocument(BaseModel):
    document_type: str

    vessel_name: Optional[ExtractedField] = None
    imo_number: Optional[ExtractedField] = None
    call_sign: Optional[ExtractedField] = None
    gross_tonnage: Optional[ExtractedField] = None
    flag: Optional[ExtractedField] = None

    issue_date: Optional[ExtractedField] = None
    expiry_date: Optional[ExtractedField] = None
    issuing_authority: Optional[ExtractedField] = None