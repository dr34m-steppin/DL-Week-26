import io

from pypdf import PdfReader


def extract_text_from_pdf_bytes(raw_bytes: bytes) -> str:
    with io.BytesIO(raw_bytes) as stream:
        reader = PdfReader(stream)
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
    return "\n".join(texts).strip()
