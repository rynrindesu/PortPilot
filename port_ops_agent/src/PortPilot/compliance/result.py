from typing import Optional

from pydantic import BaseModel, Field


class ComplianceIssue(BaseModel):

    code: str
    message: str
    severity: str

    document_type: Optional[str] = None
    field: Optional[str] = None


class ComplianceResult(BaseModel):

    status: str

    issues: list[ComplianceIssue] = Field(
        default_factory=list
    )