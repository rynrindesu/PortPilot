from pydantic import BaseModel
from typing import Optional


class PortCall(BaseModel):

    vessel_name: Optional[str] = None
    imo_number: Optional[str] = None
    call_sign: Optional[str] = None

    phase: str

    first_singapore_call: bool = False

    purpose_of_call: Optional[str] = None

    carrying_dangerous_goods: bool = False

    radioactive_material: bool = False

    next_port: Optional[str] = None