#!/usr/bin/env python3
"""Generate sample PDF files for testing edge cases and load validation.

Files created in delivery/samples/:
  1. normal.pdf             - Valid 3-page text document with headings and paragraphs.
  2. large_200p.pdf         - Valid 200-page document for heavy extraction testing.
  3. encrypted.pdf          - Password-protected PDF (password: 'secret123').
  4. corrupt.pdf            - Truncated / malformed PDF binary.
  5. scanned_image_only.pdf - Image-only document with zero extractable text elements.
  6. not_a_pdf.pdf          - Plain text file disguised with a .pdf extension.
"""

import io
import sys
from pathlib import Path

try:
    import pypdf
except ImportError:
    print("pypdf is required. Install via 'pip install pypdf' or run with uv.", file=sys.stderr)
    sys.exit(1)


def make_page_pdf(text_lines: list[str]) -> bytes:
    """Create a single-page valid PDF with the given lines of text."""
    stream_content = "BT\n/F1 14 Tf\n50 750 Td\n20 TL\n"
    for line in text_lines:
        safe_line = line.replace("(", "\\(").replace(")", "\\)")
        stream_content += f"({safe_line}) '\n"
    stream_content += "ET"
    stream_bytes = stream_content.encode("latin1")

    raw_pdf = f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length {len(stream_bytes)} >>
stream
{stream_content}
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000227 00000 n 
0000000334 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
450
%%EOF"""

    reader = pypdf.PdfReader(io.BytesIO(raw_pdf.encode("latin1")))
    writer = pypdf.PdfWriter()
    writer.append(reader)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def generate_all_samples(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generating sample test PDFs in: {output_dir.resolve()}")

    # 1. normal.pdf (3 pages of text)
    writer_normal = pypdf.PdfWriter()
    page1 = pypdf.PdfReader(
        io.BytesIO(
            make_page_pdf(
                [
                    "ANNUAL PERFORMANCE REPORT - FY2026",
                    "Section 1: Executive Overview",
                    "The organization achieved outstanding growth across all core segments.",
                    "Total revenue increased by 34.2% year-over-year.",
                    "Enterprise client retention remained strong at 98.4%.",
                ]
            )
        )
    ).pages[0]
    page2 = pypdf.PdfReader(
        io.BytesIO(
            make_page_pdf(
                [
                    "Section 2: Operational Highlights and Platform Scaling",
                    "Asynchronous processing infrastructure successfully scaled to 500k jobs/day.",
                    "End-to-end processing latency was reduced by 45%.",
                    "Automated multimodal parsing provided comprehensive visual extraction.",
                ]
            )
        )
    ).pages[0]
    page3 = pypdf.PdfReader(
        io.BytesIO(
            make_page_pdf(
                [
                    "Section 3: Strategic Outlook and Recommendations",
                    "Continued investment in distributed worker orchestration.",
                    "Expansion of multi-region high availability architectures.",
                    "Approved by the Board of Directors on October 31, 2026.",
                ]
            )
        )
    ).pages[0]
    writer_normal.add_page(page1)
    writer_normal.add_page(page2)
    writer_normal.add_page(page3)

    normal_path = output_dir / "normal.pdf"
    with open(normal_path, "wb") as f:
        writer_normal.write(f)
    print(f"  [x] normal.pdf (3 pages, {normal_path.stat().st_size} bytes)")

    # 2. large_200p.pdf (200 pages)
    writer_large = pypdf.PdfWriter()
    for i in range(1, 201):
        p = pypdf.PdfReader(
            io.BytesIO(
                make_page_pdf(
                    [
                        f"LARGE DOCUMENT VOLUME TEST - PAGE {i} OF 200",
                        f"Automated stress testing record sequence #{i}.",
                        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
                        "Integer nec odio. Praesent libero. Sed cursus ante dapibus diam.",
                        "Sed nisi. Nulla quis sem at nibh elementum imperdiet.",
                    ]
                )
            )
        ).pages[0]
        writer_large.add_page(p)

    large_path = output_dir / "large_200p.pdf"
    with open(large_path, "wb") as f:
        writer_large.write(f)
    print(f"  [x] large_200p.pdf (200 pages, {large_path.stat().st_size} bytes)")

    # 3. encrypted.pdf
    writer_enc = pypdf.PdfWriter()
    writer_enc.add_page(page1)
    writer_enc.encrypt("secret123")
    enc_path = output_dir / "encrypted.pdf"
    with open(enc_path, "wb") as f:
        writer_enc.write(f)
    print(f"  [x] encrypted.pdf (encrypted with 'secret123', {enc_path.stat().st_size} bytes)")

    # 4. corrupt.pdf (malformed header/trailer)
    corrupt_path = output_dir / "corrupt.pdf"
    corrupt_content = b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >>\n%%TRUNCATED_CORRUPT_BYTES\x00\xff\xfe"
    corrupt_path.write_bytes(corrupt_content)
    print(f"  [x] corrupt.pdf (corrupted binary, {corrupt_path.stat().st_size} bytes)")

    # 5. scanned_image_only.pdf (blank pages with 0 extractable text)
    writer_scan = pypdf.PdfWriter()
    writer_scan.add_blank_page(width=595, height=842)
    writer_scan.add_blank_page(width=595, height=842)
    scan_path = output_dir / "scanned_image_only.pdf"
    with open(scan_path, "wb") as f:
        writer_scan.write(f)
    print(f"  [x] scanned_image_only.pdf (0 extractable text, {scan_path.stat().st_size} bytes)")

    # 6. not_a_pdf.pdf (plain text disguised as PDF)
    fake_path = output_dir / "not_a_pdf.pdf"
    fake_path.write_text(
        "This is not a real PDF file.\nIt contains plain UTF-8 text and lacks PDF magic bytes.\n",
        encoding="utf-8",
    )
    print(f"  [x] not_a_pdf.pdf (spoofed extension, {fake_path.stat().st_size} bytes)")


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "samples"
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    generate_all_samples(target)
