from typing import Optional

from pydantic import BaseModel


class ComplianceIssue(BaseModel):
    code: str
    message: str
    severity: str
    document_type: Optional[str] = None
    field: Optional[str] = None


class ComplianceResult(BaseModel):
    status: str
    issues: list[ComplianceIssue] = []