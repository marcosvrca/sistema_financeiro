"""Testes de isolamento de dados entre usuários (multi-tenant)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

os.environ.pop("DATABASE_URL", None)

import financeiro.config as cfg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
from financeiro.db import init_db, inserir_lancamento_manual  # noqa: E402


class TenantIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._db = Path(cls._tmpdir.name) / "marcos.db"
        cls._users_dir = Path(cls._tmpdir.name) / "users"
        cls._orig_sqlite = cfg.SQLITE_PATH
        cls._orig_users_dir = cfg.USERS_DATA_DIR
        cfg.SQLITE_PATH = cls._db
        cfg.USERS_DATA_DIR = cls._users_dir
        cls._users_dir.mkdir(parents=True, exist_ok=True)
        init_db(cls._db)
        init_db(cls._users_dir / "vitoria.db")

        inserir_lancamento_manual(
            cls._db,
            data_mov=date(2026, 7, 1),
            descricao="LANCAMENTO_SECRETO_MARCOS",
            valor=Decimal("1234.56"),
            tipo="entrada",
            categoria="Outros",
        )

        cls.client = TestClient(api.app)

        marcos_login = cls.client.post(
            "/api/auth/login",
            json={"email": "marcosviniciusrdca2@gmail.com", "password": "250922"},
        )
        cls._auth_marcos = {"Authorization": "Bearer " + marcos_login.json()["token"]}

        vitoria_login = cls.client.post(
            "/api/auth/login",
            json={"email": "vitoriasrochapereira@gmail.com", "password": "250922"},
        )
        cls._auth_vitoria = {"Authorization": "Bearer " + vitoria_login.json()["token"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cfg.SQLITE_PATH = cls._orig_sqlite
        cfg.USERS_DATA_DIR = cls._orig_users_dir
        cls._tmpdir.cleanup()

    def test_marcos_ve_seu_lancamento(self) -> None:
        r = self.client.get(
            "/api/lancamentos?de=2026-07-01&ate=2026-07-31",
            headers=self._auth_marcos,
        )
        self.assertEqual(r.status_code, 200)
        descricoes = [x["descricao"] for x in r.json()]
        self.assertIn("LANCAMENTO_SECRETO_MARCOS", descricoes)

    def test_vitoria_nao_ve_dados_marcos(self) -> None:
        r = self.client.get(
            "/api/lancamentos?de=2026-07-01&ate=2026-07-31",
            headers=self._auth_vitoria,
        )
        self.assertEqual(r.status_code, 200)
        descricoes = [x["descricao"] for x in r.json()]
        self.assertNotIn("LANCAMENTO_SECRETO_MARCOS", descricoes)

    def test_vitoria_grava_no_proprio_banco(self) -> None:
        r = self.client.post(
            "/api/lancamentos",
            json={
                "data": "2026-07-02",
                "descricao": "LANCAMENTO_VITORIA_ISOLADO",
                "valor": "50,00",
                "tipo": "saida",
                "categoria": "Outros",
            },
            headers=self._auth_vitoria,
        )
        self.assertEqual(r.status_code, 200)
        lid = r.json()["id"]

        rv = self.client.get(
            "/api/lancamentos?de=2026-07-01&ate=2026-07-31",
            headers=self._auth_vitoria,
        )
        self.assertTrue(any(x["id"] == lid for x in rv.json()))

        rm = self.client.get(
            "/api/lancamentos?de=2026-07-01&ate=2026-07-31",
            headers=self._auth_marcos,
        )
        self.assertFalse(any(x["id"] == lid for x in rm.json()))

    def test_tokens_sao_de_usuarios_diferentes(self) -> None:
        me_m = self.client.get("/api/auth/me", headers=self._auth_marcos).json()
        me_v = self.client.get("/api/auth/me", headers=self._auth_vitoria).json()
        self.assertEqual(me_m["id"], "marcos")
        self.assertEqual(me_v["id"], "vitoria")

    def test_importar_arquivo_extrato(self) -> None:
        exemplo = (
            "Data;Histórico;Docto.;Crédito (R$);Débito (R$);Saldo (R$)\n"
            "01/07/2026;TESTE IMPORT ARQUIVO;1;100,00; ;100,00\n"
        )
        r = self.client.post(
            "/api/extrato/importar-arquivo",
            headers=self._auth_marcos,
            files={"arquivo": ("extrato.csv", exemplo.encode("utf-8"), "text/csv")},
            data={"banco": "bradesco"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertGreater(body.get("inseridas", 0), 0)


if __name__ == "__main__":
    unittest.main()
