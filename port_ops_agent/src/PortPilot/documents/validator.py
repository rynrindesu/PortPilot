import re


def validate_imo_number(imo_number: str) -> bool:
    """
    Validate the basic format of an IMO number.

    An IMO number consists of exactly 7 digits.
    """

    if not imo_number:
        return False

    return bool(re.fullmatch(r"\d{7}", imo_number))


def validate_extracted_document(document):
    """
    Validate fields in an extracted document.

    Returns:
        list[str]: Validation errors.
    """

    errors = []

    if document.imo_number is not None:
        imo = document.imo_number.value

        if imo is not None:
            if not isinstance(imo, str):
                imo = str(imo)

            if not validate_imo_number(imo):
                errors.append(
                    f"Invalid IMO number format: {imo}"
                )

    return errors