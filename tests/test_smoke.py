"""Testes de fumaça para API e módulos críticos."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

# Garante SQLite isolado nos testes (sem Postgres do ambiente).
os.environ.pop("DATABASE_URL", None)

import financeiro.config as cfg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
from financeiro.db import (  # noqa: E402
    excluir_lancamento_manual,
    init_db,
    inserir_lancamento_manual,
    listar_lancamentos_manuais,
)
from financeiro.features import resumo_investimentos  # noqa: E402


class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._db = Path(cls._tmpdir.name) / "test.db"
        cls._orig_sqlite = cfg.SQLITE_PATH
        cfg.SQLITE_PATH = cls._db
        init_db(cls._db)
        cls.client = TestClient(api.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cfg.SQLITE_PATH = cls._orig_sqlite
        cls._tmpdir.cleanup()

    def test_health_ok(self) -> None:
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_homepage(self) -> None:
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("content-type", ""))

    def test_categorias(self) -> None:
        r = self.client.get("/api/categorias")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)
        self.assertGreater(len(r.json()), 0)

    def test_indicadores_periodo(self) -> None:
        r = self.client.get("/api/indicadores?de=2026-01-01&ate=2026-12-31")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("entradas", body)
        self.assertIn("saidas", body)

    def test_data_invalida_retorna_400(self) -> None:
        r = self.client.get("/api/indicadores?de=invalido")
        self.assertEqual(r.status_code, 400)

    def test_mes_invalido_retorna_400(self) -> None:
        r = self.client.get("/api/calendario?mes=2026")
        self.assertEqual(r.status_code, 400)

    def test_investimentos_resumo(self) -> None:
        r = self.client.get("/api/investimentos/resumo")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("patrimonio_total", body)

    def test_lancamentos_api(self) -> None:
        r = self.client.post(
            "/api/lancamentos",
            json={
                "data": "2026-06-01",
                "descricao": "Teste API",
                "valor": "25,00",
                "tipo": "saida",
                "categoria": "Outros",
            },
        )
        self.assertEqual(r.status_code, 200)
        lid = r.json()["id"]
        listed = self.client.get("/api/lancamentos?de=2026-06-01&ate=2026-06-30")
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(x["id"] == lid for x in listed.json()))
        deleted = self.client.delete(f"/api/lancamentos/{lid}")
        self.assertEqual(deleted.status_code, 200)
        missing = self.client.delete(f"/api/lancamentos/{lid}")
        self.assertEqual(missing.status_code, 404)

    def test_lancamentos_crud_db(self) -> None:
        lid = inserir_lancamento_manual(
            self._db,
            data_mov=date(2026, 6, 1),
            descricao="Teste",
            valor=Decimal("10.50"),
            tipo="saida",
            categoria="Outros",
        )
        rows = listar_lancamentos_manuais(date(2026, 6, 1), date(2026, 6, 30), self._db)
        self.assertTrue(any(r["id"] == lid for r in rows))
        self.assertTrue(excluir_lancamento_manual(self._db, lid))
        self.assertFalse(excluir_lancamento_manual(self._db, lid))

    def test_resumo_investimentos_sqlite(self) -> None:
        r = resumo_investimentos(self._db)
        self.assertIn("patrimonio_total", r)
        self.assertEqual(r["qtd_ativos"], 0)


if __name__ == "__main__":
    unittest.main()
