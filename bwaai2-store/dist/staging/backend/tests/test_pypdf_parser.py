import pytest

from app.core.exceptions import EncryptedPDFError
from app.models.documents import ContentFormat
from app.services.parsers.pypdf_parser import PyPDFParser
from tests.conftest import create_sample_encrypted_pdf, create_sample_pdf


@pytest.mark.asyncio
async def test_pypdf_parser_valid_pdf() -> None:
    parser = PyPDFParser()
    pdf_bytes = create_sample_pdf(num_pages=3)

    pages = await parser.parse(pdf_bytes)

    assert len(pages) == 3
    for idx, page in enumerate(pages):
        assert page.page_number == idx + 1
        assert page.format == ContentFormat.text
        assert isinstance(page.content, str)


@pytest.mark.asyncio
async def test_pypdf_parser_encrypted_pdf() -> None:
    parser = PyPDFParser()
    encrypted_bytes = create_sample_encrypted_pdf(password="testpass")

    with pytest.raises(EncryptedPDFError) as exc_info:
        await parser.parse(encrypted_bytes)

    assert exc_info.value.code == "ENCRYPTED_PDF"
