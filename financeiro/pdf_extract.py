"""Extração de texto de extratos em PDF."""

from __future__ import annotations

import io


def extrair_texto_pdf(conteudo: bytes) -> str:
    """Extrai texto de um PDF (extratos digitais, sem OCR)."""
    if not conteudo:
        return ""
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "Suporte a PDF requer pdfplumber. Instale com: pip install pdfplumber"
        ) from exc

    partes: list[str] = []
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            if texto.strip():
                partes.append(texto)
    return "\n".join(partes)
