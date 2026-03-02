#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path
from typing import List


def _normalize_markdown_line(line: str) -> str:
    s = line.rstrip("\n").replace("\t", "    ")

    # Convert links to "label (url)" to keep references visible in PDF.
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)

    # Strip common markdown emphasis tokens.
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
    s = re.sub(r"__(.*?)__", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)

    # Headers: retain hierarchy with prefix markers.
    m = re.match(r"^(#{1,6})\s+(.*)$", s)
    if m:
        level = len(m.group(1))
        title = m.group(2).strip()
        if level == 1:
            return title.upper()
        if level == 2:
            return f"{title}"
        return f"- {title}"

    # Normalize list bullets.
    s = re.sub(r"^\s*[-*]\s+", "- ", s)
    s = re.sub(r"^\s*\d+\.\s+", "- ", s)
    return s


def _markdown_to_wrapped_lines(md_text: str, width: int = 94) -> List[str]:
    raw_lines = md_text.splitlines()
    out: List[str] = []
    for raw in raw_lines:
        normalized = _normalize_markdown_line(raw)
        if not normalized.strip():
            out.append("")
            continue
        wrapped = textwrap.wrap(
            normalized,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        if wrapped:
            out.extend(wrapped)
        else:
            out.append("")
    return out


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf_content(lines: List[str], page_line_count: int = 54) -> List[bytes]:
    pages: List[bytes] = []
    for i in range(0, len(lines), page_line_count):
        chunk = lines[i : i + page_line_count]
        cmds = ["BT", "/F1 10 Tf", "50 760 Td", "13 TL"]
        for line in chunk:
            cmds.append(f"({_pdf_escape(line)}) Tj")
            cmds.append("T*")
        cmds.append("ET")
        content = "\n".join(cmds).encode("latin-1", errors="replace")
        pages.append(content)
    if not pages:
        pages.append(b"BT\n/F1 10 Tf\n50 760 Td\n(Empty document) Tj\nET\n")
    return pages


def build_pdf_from_markdown(md_path: Path, pdf_path: Path) -> None:
    md_text = md_path.read_text(encoding="utf-8")
    lines = _markdown_to_wrapped_lines(md_text)
    page_streams = _build_pdf_content(lines)

    # Object plan:
    # 1 catalog, 2 pages, 3 font, then for each page: page obj + content stream obj
    objects: List[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")

    page_count = len(page_streams)
    first_page_obj = 4
    kids_refs = []
    for idx in range(page_count):
        page_obj_id = first_page_obj + idx * 2
        kids_refs.append(f"{page_obj_id} 0 R")
    kids_str = " ".join(kids_refs).encode("ascii")
    objects.append(b"<< /Type /Pages /Kids [" + kids_str + b"] /Count " + str(page_count).encode("ascii") + b" >>")

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for idx, stream in enumerate(page_streams):
        page_obj_id = first_page_obj + idx * 2
        stream_obj_id = page_obj_id + 1
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_obj_id} 0 R >>"
        ).encode("ascii")
        stream_obj = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
        objects.append(page_obj)
        objects.append(stream_obj)

    # Assemble file
    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]  # xref entry 0

    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_start = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    trailer = (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n"
    ).encode("ascii")
    out.extend(trailer)

    pdf_path.write_bytes(bytes(out))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: build_docs_pdf.py <input.md> <output.pdf>")
        return 1

    md_path = Path(sys.argv[1]).resolve()
    pdf_path = Path(sys.argv[2]).resolve()

    if not md_path.exists():
        print(f"Input markdown not found: {md_path}")
        return 1

    build_pdf_from_markdown(md_path, pdf_path)
    print(f"Wrote PDF: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
