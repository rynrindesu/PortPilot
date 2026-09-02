from PortPilot.documents.classifier import classify_document
from PortPilot.documents.validator import validate_imo_number


def test_certificate_classification():
    text = """
    CERTIFICATE OF REGISTRY
    Vessel Name: EVER EXAMPLE
    """

    result = classify_document(text)

    assert result == "certificate_of_registry"


def test_cargo_manifest_classification():
    text = """
    CARGO MANIFEST
    Vessel Name: EVER EXAMPLE
    """

    result = classify_document(text)

    assert result == "cargo_manifest"


def test_valid_imo():
    assert validate_imo_number("9876543") is True


def test_invalid_imo():
    assert validate_imo_number("12345") is False