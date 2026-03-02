"""Generate a simple PDF from markdown/plain text without external dependencies."""

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SOURCE = BASE / "docs" / "PROJECT_DOCUMENTATION.md"
OUTPUT = BASE / "docs" / "PROJECT_DOCUMENTATION.pdf"


def escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(lines):
    # Basic PDF with built-in Helvetica font.
    objects = []

    def add_object(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    font_obj = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_width = 595
    page_height = 842
    margin_x = 50
    margin_y = 60
    line_height = 14

    pages = []
    current_page_lines = []
    max_lines = (page_height - 2 * margin_y) // line_height

    for line in lines:
        if len(current_page_lines) >= max_lines:
            pages.append(current_page_lines)
            current_page_lines = []
        current_page_lines.append(line)

    if current_page_lines:
        pages.append(current_page_lines)

    page_objs = []

    for page_lines in pages:
        content_cmds = [b"BT", b"/F1 11 Tf", f"{margin_x} {page_height - margin_y} Td".encode()]
        for idx, line in enumerate(page_lines):
            if idx == 0:
                content_cmds.append(f"({escape_pdf_text(line)}) Tj".encode())
            else:
                content_cmds.append(f"0 -{line_height} Td ({escape_pdf_text(line)}) Tj".encode())
        content_cmds.append(b"ET")
        stream = b"\n".join(content_cmds)
        content_obj = add_object(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

        page_obj = add_object(
            (
                "<< /Type /Page /Parent {PAGES} 0 R /MediaBox [0 0 "
                f"{page_width} {page_height}] /Resources << /Font << /F1 {font_obj} 0 R >> >> "
                f"/Contents {content_obj} 0 R >>"
            ).encode()
        )
        page_objs.append(page_obj)

    kids = " ".join([f"{obj} 0 R" for obj in page_objs])
    pages_obj = add_object(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_objs)} >>".encode()
    )

    # Replace placeholder parent reference now that pages object id is known.
    for i, obj in enumerate(objects):
        if b"{PAGES}" in obj:
            objects[i] = obj.replace(b"{PAGES}", str(pages_obj).encode())

    catalog_obj = add_object(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode())

    # Write file
    out = bytearray()
    out.extend(b"%PDF-1.4\n")

    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())

    out.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root {catalog_obj} 0 R >>\n"
            "startxref\n"
            f"{xref_pos}\n"
            "%%EOF\n"
        ).encode()
    )

    return out


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            lines.append(" ")
            continue
        # Soft wrap long lines
        while len(line) > 95:
            cut = line.rfind(" ", 0, 95)
            if cut < 50:
                cut = 95
            lines.append(line[:cut])
            line = line[cut:].strip()
        lines.append(line)

    pdf_bytes = build_pdf(lines)
    OUTPUT.write_bytes(pdf_bytes)
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    main()
