from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PortCallPhase(str, Enum):
    """
    The current stage of the vessel's port call.
    """

    ARRIVAL = "arrival"
    OPERATIONS = "operations"
    DEPARTURE = "departure"


class PortCallStatus(str, Enum):
    """
    The current status of the port call.
    """

    CREATED = "created"

    ARRIVAL_PENDING = "arrival_pending"
    ARRIVAL_CHECKING = "arrival_checking"
    ARRIVAL_CLEARED = "arrival_cleared"

    OPERATIONS = "operations"

    DEPARTURE_PENDING = "departure_pending"
    DEPARTURE_CHECKING = "departure_checking"
    DEPARTURE_CLEARED = "departure_cleared"

    CORRECTION_REQUIRED = "correction_required"
    HUMAN_REVIEW = "human_review"
    INSPECTION_REQUIRED = "inspection_required"

    COMPLETED = "completed"


class PortCallState(BaseModel):
    """
    Represents the current state of a vessel's port call.
    """

    # --------------------------------
    # Port call identity
    # --------------------------------

    port_call_id: str

    vessel_name: Optional[str] = None
    imo_number: Optional[str] = None
    call_sign: Optional[str] = None

    # --------------------------------
    # Current workflow stage
    # --------------------------------

    phase: PortCallPhase

    status: PortCallStatus

    # --------------------------------
    # Port-call information
    # --------------------------------

    first_singapore_call: bool = False

    purpose_of_call: Optional[str] = None

    # --------------------------------
    # Cargo risk information
    # --------------------------------

    carrying_dangerous_goods: bool = False

    radioactive_material: bool = False

    # --------------------------------
    # Submitted documents
    # --------------------------------

    documents: list = Field(default_factory=list)