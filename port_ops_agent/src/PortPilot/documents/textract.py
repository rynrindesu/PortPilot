from pathlib import Path


def mock_textract(file_path: str) -> dict:
    """
    Mock Amazon Textract response.

    Used during local development when AWS access
    is not available.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(file_path)

    # Simulated Textract response
    return {
        "Blocks": [
            {
                "BlockType": "LINE",
                "Text": "CERTIFICATE OF REGISTRY",
                "Confidence": 99.5,
            },
            {
                "BlockType": "LINE",
                "Text": "Vessel Name: EVER EXAMPLE",
                "Confidence": 98.7,
            },
            {
                "BlockType": "LINE",
                "Text": "IMO Number: 9876543",
                "Confidence": 99.1,
            },
            {
                "BlockType": "LINE",
                "Text": "Call Sign: 9V1234",
                "Confidence": 98.3,
            },
            {
                "BlockType": "LINE",
                "Text": "Gross Tonnage: 82500",
                "Confidence": 97.8,
            },
            {
                "BlockType": "LINE",
                "Text": "Flag: Singapore",
                "Confidence": 99.0,
            },
        ]
    }


def extract_text_from_mock_textract(response: dict) -> str:
    """
    Convert Textract-style Blocks into plain text.
    """

    lines = []

    for block in response["Blocks"]:
        if block["BlockType"] == "LINE":
            lines.append(block["Text"])

    return "\n".join(lines)