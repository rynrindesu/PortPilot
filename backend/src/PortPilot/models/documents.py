from typing import Optional, Union

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):

    value: Optional[Union[str, float, int, bool]] = None

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    source_text: Optional[str] = None


class ExtractedDocument(BaseModel):

    document_type: str

    # Vessel identity
    vessel_name: Optional[ExtractedField] = None
    imo_number: Optional[ExtractedField] = None
    call_sign: Optional[ExtractedField] = None
    gross_tonnage: Optional[ExtractedField] = None
    flag: Optional[ExtractedField] = None

    vessel_type: Optional[ExtractedField] = None
    port_of_registry: Optional[ExtractedField] = None
    official_number: Optional[ExtractedField] = None

    # Ownership
    vessel_owner: Optional[ExtractedField] = None
    charterer_nationality: Optional[ExtractedField] = None

    # Dates
    issue_date: Optional[ExtractedField] = None
    expiry_date: Optional[ExtractedField] = None

    arrival_date_time: Optional[ExtractedField] = None
    departure_date_time: Optional[ExtractedField] = None

    # Port call
    purpose_of_call: Optional[ExtractedField] = None
    last_port: Optional[ExtractedField] = None
    next_port: Optional[ExtractedField] = None

    # People
    master: Optional[ExtractedField] = None
    crew: Optional[ExtractedField] = None
    passengers: Optional[ExtractedField] = None

    # Cargo
    total_cargo: Optional[ExtractedField] = None

    # Authority
    issuing_authority: Optional[ExtractedField] = None