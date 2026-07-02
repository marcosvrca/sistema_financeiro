"""Testes dos parsers de extrato em PDF."""

from __future__ import annotations

import unittest
from pathlib import Path

from financeiro.pdf_extract import extrair_texto_pdf
from financeiro.pdf_parser import (
    eh_extrato_brb_pdf,
    eh_extrato_nubank_pdf,
    parse_brb_pdf,
    parse_extrato_pdf,
    parse_nubank_pdf,
)

NUBANK_PDF = Path(r"c:\Users\04510018185\Downloads\NU_188171812_01JUN2026_30JUN2026.pdf")
BRB_PDF = Path(r"c:\Users\04510018185\Downloads\extrato.pdf")


@unittest.skipUnless(NUBANK_PDF.is_file(), "PDF Nubank de referência não encontrado")
class NubankPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.texto = extrair_texto_pdf(NUBANK_PDF.read_bytes())

    def test_detecta_formato(self) -> None:
        self.assertTrue(eh_extrato_nubank_pdf(self.texto))

    def test_importa_movimentos(self) -> None:
        linhas = parse_nubank_pdf(self.texto)
        self.assertGreater(len(linhas), 20)
        self.assertTrue(any("RESTAURANTE" in r.historico for r in linhas))
        self.assertTrue(any(r.credito is not None for r in linhas))
        self.assertTrue(any(r.debito is not None for r in linhas))


@unittest.skipUnless(BRB_PDF.is_file(), "PDF BRB de referência não encontrado")
class BrbPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.texto = extrair_texto_pdf(BRB_PDF.read_bytes())

    def test_detecta_formato(self) -> None:
        self.assertTrue(eh_extrato_brb_pdf(self.texto))

    def test_importa_movimentos(self) -> None:
        linhas = parse_brb_pdf(self.texto)
        self.assertGreater(len(linhas), 15)
        self.assertTrue(any(r.debito is not None for r in linhas))
        self.assertTrue(any(r.credito is not None for r in linhas))

    def test_parse_extrato_pdf_com_banco(self) -> None:
        linhas = parse_extrato_pdf(self.texto, banco="BRB")
        self.assertGreater(len(linhas), 10)


if __name__ == "__main__":
    unittest.main()
