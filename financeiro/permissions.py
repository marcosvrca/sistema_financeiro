"""Regras de permissão e isolamento por usuário (tenant)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from financeiro.auth import USERS_BY_ID, is_known_user_id

# Rotas da API acessíveis sem contexto de usuário autenticado.
PUBLIC_API_PATHS = frozenset(
    {
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
    }
)


def is_protected_api_path(path: str, method: str) -> bool:
    if method == "OPTIONS":
        return False
    return path.startswith("/api/") and path not in PUBLIC_API_PATHS


def get_request_user_id(request: Request) -> str | None:
    return getattr(request.state, "user_id", None)


def require_request_user_id(request: Request) -> str:
    """Exige usuário autenticado na requisição (após middleware de auth)."""
    uid = get_request_user_id(request)
    if not uid:
        raise HTTPException(403, "Contexto de usuário ausente.")
    assert_valid_tenant(uid)
    return uid


def assert_valid_tenant(user_id: str) -> None:
    """Garante que o id pertence a um usuário registrado no sistema."""
    if not is_known_user_id(user_id):
        raise HTTPException(403, "Usuário não autorizado.")


class TenantContextRequired(RuntimeError):
    """Banco acessado sem tenant definido (falha fechada)."""
